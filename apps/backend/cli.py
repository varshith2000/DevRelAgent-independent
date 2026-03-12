#!/usr/bin/env python3
"""
DevRelAgent CLI — Command-Line Interface

Production-grade CLI for interacting with DevRelAgent.
Supports dry-run, JSON output, approval flags, and more.

Usage:
    # Interactive mode
    python cli.py investigate "Why is the API slow?"

    # Dry-run mode (no actions taken)
    python cli.py investigate "API errors" --dry-run

    # JSON output
    python cli.py investigate "Database latency" --json

    # Bypass approvals (use with caution)
    python cli.py investigate "Create dashboard" --auto-approve

    # Get status
    python cli.py status

    # List investigations
    python cli.py list-investigations
"""

import asyncio
import json
import logging
import sys
import argparse
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from agent.loop import AgentLoop
from memory.investigation_store import get_investigation_store
from models.schemas import StructuredAgentResponse, InvestigationState
from tools.registry import get_registry

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DevRelAgentCLI:
    """
    DevRelAgent CLI - Production-grade command-line interface.

    Features:
    - Dry-run mode for testing
    - JSON output for automation
    - Auto-approve for batch operations
    - Investigation tracking
    - Audit logging
    """

    def __init__(self, verbose: bool = False):
        """Initialize CLI."""
        self.agent = AgentLoop()
        self.store = get_investigation_store()
        self.dry_run = False
        self.auto_approve = False
        self.json_output = False
        self.verbose = verbose
        self.audit_log = []
        self.session_id = None

    def log_audit_event(self, event_type: str, data: Dict[str, Any]):
        """Log audit event."""
        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "data": data
        }
        self.audit_log.append(event)
        logger.info(f"[AUDIT] {event_type}: {json.dumps(data, indent=2)}")

    async def investigate(
        self,
        query: str,
        dry_run: bool = False,
        auto_approve: bool = False,
        json_output: bool = False,
        save_investigation: bool = True,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run an investigation query.

        Args:
            query: Investigation query
            dry_run: Don't execute write operations
            auto_approve: Auto-approve all actions
            json_output: Return JSON-formatted response
            save_investigation: Save investigation to store

        Returns:
            Investigation results
        """
        try:
            # Set session ID
            if session_id:
                self.session_id = session_id
                if self.verbose:
                    logger.info(f"[VERBOSE] Using session ID: {session_id}")
            else:
                self.session_id = f"sess_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                if self.verbose:
                    logger.info(f"[VERBOSE] Created new session: {self.session_id}")

            # Create investigation state
            investigation_id = f"inv_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            if self.verbose:
                logger.info(f"[VERBOSE] Created investigation ID: {investigation_id}")
                logger.info(f"[VERBOSE] Dry-run mode: {dry_run}")
                logger.info(f"[VERBOSE] Auto-approve: {auto_approve}")
                logger.info(f"[VERBOSE] Save investigation: {save_investigation}")

            investigation = InvestigationState(
                investigation_id=investigation_id,
                title=query[:100],
                description=f"CLI investigation: {query}",
                status="in_progress",
                initial_query=query,
                started_at=datetime.now().isoformat()
            )

            # Log audit event
            self.log_audit_event("investigation_started", {
                "investigation_id": investigation_id,
                "session_id": self.session_id,
                "query": query,
                "dry_run": dry_run,
                "auto_approve": auto_approve
            })

            # Process query
            logger.info(f"Investigating: {query}")

            if self.verbose:
                logger.info(f"[VERBOSE] Processing query with agent loop...")
                logger.info(f"[VERBOSE] Query length: {len(query)} characters")

            # Create SessionContext from session_id
            from models.schemas import SessionContext
            session_context = SessionContext(session_id=self.session_id)

            response_text, tool_calls = await self.agent.process_with_tools(
                query,
                session=session_context
            )

            # Check if HITL approval is required
            hitl_required = False
            if tool_calls:
                for tc in tool_calls:
                    # Check if tool result has HITL requirement
                    if hasattr(tc, 'result') and isinstance(tc.result, dict):
                        if tc.result.get('hitl_required') or tc.result.get('requires_approval'):
                            hitl_required = True
                            break

            # Check if response contains HITL requirement note
            if "[Note: This action requires human approval before execution.]" in response_text:
                hitl_required = True

            # If HITL is required and not auto_approve, prompt for approval
            if hitl_required and not auto_approve and not dry_run:
                print(f"\n{'='*60}")
                print("HUMAN APPROVAL REQUIRED")
                print(f"{'='*60}")
                print(f"\nThe following action requires your approval:")
                print(f"\nQuery: {query}")

                if tool_calls:
                    print(f"\nTools to be executed:")
                    for tc in tool_calls:
                        print(f"  - {tc.tool_name}")

                print(f"\nResponse preview:")
                preview = response_text.split('[Note:')[0].strip()
                if len(preview) > 200:
                    preview = preview[:200] + "..."
                print(f"  {preview}")

                print(f"\n{'='*60}")

                # Prompt for approval
                while True:
                    user_input = input("\nDo you approve this action? (approve/reject/cancel): ").strip().lower()

                    if user_input in ['approve', 'yes', 'y', 'ok']:
                        print("\n[INFO] Action approved by user. Proceeding...")
                        # Log approval
                        self.log_audit_event("hitl_approval", {
                            "investigation_id": investigation_id,
                            "query": query,
                            "decision": "approved",
                            "tools_used": [tc.tool_name for tc in tool_calls]
                        })
                        break
                    elif user_input in ['reject', 'no', 'n']:
                        print("\n[INFO] Action rejected by user. Cancelling...")
                        self.log_audit_event("hitl_approval", {
                            "investigation_id": investigation_id,
                            "query": query,
                            "decision": "rejected"
                        })
                        return {
                            "success": False,
                            "error": "Action rejected by user",
                            "investigation_id": investigation_id
                        }
                    elif user_input in ['cancel', 'exit', 'quit', 'q']:
                        print("\n[INFO] Cancelled by user.")
                        self.log_audit_event("hitl_approval", {
                            "investigation_id": investigation_id,
                            "query": query,
                            "decision": "cancelled"
                        })
                        return {
                            "success": False,
                            "error": "Action cancelled by user",
                            "investigation_id": investigation_id
                        }
                    else:
                        print("\nInvalid input. Please enter 'approve', 'reject', or 'cancel':")

            # Remove the HITL note from response if approved
            if "[Note: This action requires human approval before execution.]" in response_text:
                response_text = response_text.split('[Note:')[0].strip()

            if self.verbose:
                logger.info(f"[VERBOSE] Agent processing complete")
                logger.info(f"[VERBOSE] Response length: {len(response_text)} characters")
                if tool_calls:
                    logger.info(f"[VERBOSE] Number of tool calls: {len(tool_calls)}")

            # Update investigation
            investigation.status = "completed"
            investigation.completed_at = datetime.now().isoformat()
            investigation.observations = []  # Would be populated by structured response

            if tool_calls:
                investigation.tools_used = [tc.tool_name for tc in tool_calls]
                investigation.queries_executed = len(tool_calls)

            # Save investigation if not dry-run
            if not dry_run and save_investigation:
                self.store.save_investigation(investigation)
                self.log_audit_event("investigation_saved", {
                    "investigation_id": investigation_id
                })

            # Format output
            if json_output:
                return {
                    "success": True,
                    "investigation_id": investigation_id,
                    "query": query,
                    "response": response_text,
                    "tool_calls": [tc.dict() for tc in tool_calls] if tool_calls else [],
                    "dry_run": dry_run,
                    "metadata": {
                        "timestamp": datetime.now().isoformat(),
                        "tools_used": investigation.tools_used,
                        "queries_executed": investigation.queries_executed
                    }
                }
            else:
                # Human-readable output
                print(f"\n{'='*60}")
                print(f"INVESTIGATION: {investigation_id}")
                print(f"{'='*60}")
                print(f"\nQuery: {query}")
                print(f"\nResponse:\n{response_text}\n")

                if tool_calls:
                    print(f"\n{'='*60}")
                    print("TOOLS USED:")
                    for tc in tool_calls:
                        status = "[OK]" if tc.success else "[ERROR]"
                        print(f"  {status} {tc.tool_name}")
                        if tc.result:
                            print(f"     Result: {str(tc.result)[:100]}...")
                        if tc.error:
                            print(f"     Error: {tc.error}")

                return {
                    "success": True,
                    "investigation_id": investigation_id,
                    "response": response_text
                }

        except Exception as e:
            logger.error(f"Investigation failed: {e}")

            self.log_audit_event("investigation_failed", {
                "query": query,
                "error": str(e)
            })

            return {
                "success": False,
                "error": str(e),
                "investigation_id": investigation_id if 'investigation_id' in locals() else None
            }

    async def get_status(self) -> Dict[str, Any]:
        """Get agent status and statistics."""
        try:
            registry = get_registry()
            stats = self.store.get_investigation_stats()

            return {
                "agent": {
                    "status": "healthy",
                    "tools_loaded": len(registry.tool_names),
                    "tools_enabled": len([t for t in registry.list_tools() if t.metadata.enabled]),
                    "tool_names": registry.list_tool_names()
                },
                "investigations": stats,
                "audit_log_size": len(self.audit_log),
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to get status: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def list_investigations(
        self,
        status: Optional[str] = None,
        limit: int = 20,
        json_output: bool = False
    ) -> Dict[str, Any]:
        """List investigations with optional filtering."""
        try:
            investigations = self.store.list_investigations(
                status=status,
                limit=limit
            )

            if json_output:
                return {
                    "success": True,
                    "investigations": investigations,
                    "total": len(investigations)
                }
            else:
                print(f"\n{'='*60}")
                print("INVESTIGATIONS")
                print(f"{'='*60}\n")

                if not investigations:
                    print("No investigations found.")
                    return {"success": True, "investigations": []}

                for inv in investigations:
                    print(f"📋 {inv.get('investigation_id')}")
                    print(f"   Title: {inv.get('title')}")
                    print(f"   Status: {inv.get('status')}")
                    print(f"   Priority: {inv.get('priority')}")
                    print(f"   Observations: {inv.get('total_observations', 0)}")
                    print(f"   Confidence: {inv.get('confidence_score', 0):.2f}")
                    print(f"   Updated: {inv.get('updated_at')}")
                    print()

                return {
                    "success": True,
                    "investigations": investigations,
                    "total": len(investigations)
                }

        except Exception as e:
            logger.error(f"Failed to list investigations: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def export_audit_log(self, output_file: Optional[str] = None) -> Dict[str, Any]:
        """Export audit log to file."""
        try:
            if output_file is None:
                output_file = f"audit_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

            with open(output_file, 'w') as f:
                json.dump(self.audit_log, f, indent=2, default=str)

            return {
                "success": True,
                "output_file": output_file,
                "events_exported": len(self.audit_log)
            }

        except Exception as e:
            logger.error(f"Failed to export audit log: {e}")
            return {
                "success": False,
                "error": str(e)
            }


# ============== CLI Commands ==============

async def cmd_investigate(args):
    """Handle investigate command."""
    cli = DevRelAgentCLI(verbose=args.verbose)
    cli.dry_run = args.dry_run
    cli.auto_approve = args.auto_approve
    cli.json_output = args.json
    cli.session_id = args.session

    if args.verbose:
        logger.info("[VERBOSE] Starting investigation command")
        logger.info(f"[VERBOSE] Query: {args.query}")
        logger.info(f"[VERBOSE] Dry-run: {args.dry_run}")
        logger.info(f"[VERBOSE] Auto-approve: {args.auto_approve}")
        logger.info(f"[VERBOSE] JSON output: {args.json}")
        logger.info(f"[VERBOSE] Session ID: {args.session}")

    result = await cli.investigate(
        query=args.query,
        dry_run=args.dry_run,
        auto_approve=args.auto_approve,
        json_output=args.json,
        save_investigation=not args.dry_run,
        session_id=args.session
    )

    if args.json:
        print(json.dumps(result, indent=2, default=str))

    return 0 if result.get("success") else 1


async def cmd_status(args):
    """Handle status command."""
    cli = DevRelAgentCLI(verbose=args.verbose)

    if args.verbose:
        logger.info("[VERBOSE] Fetching agent status...")

    result = await cli.get_status()

    if args.verbose:
        logger.info(f"[VERBOSE] Status result success: {result.get('success')}")

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"\n{'='*60}")
        print("DEVREL AGENT STATUS")
        print(f"{'='*60}\n")

        agent_data = result.get("agent", {})
        print(f"Status: {agent_data.get('status', 'unknown')}")
        print(f"Tools Loaded: {agent_data.get('tools_loaded', 0)}")
        print(f"Tools Enabled: {agent_data.get('tools_enabled', 0)}")

        inv_data = result.get("investigations", {})
        print(f"\nInvestigations: {inv_data.get('total', 0)}")

        by_status = inv_data.get("by_status", {})
        if by_status:
            print("  By Status:")
            for status, count in by_status.items():
                print(f"    {status}: {count}")

    return 0 if result.get("success") else 1


async def cmd_list_investigations(args):
    """Handle list-investigations command."""
    cli = DevRelAgentCLI(verbose=args.verbose)

    if args.verbose:
        logger.info(f"[VERBOSE] Listing investigations with status={args.status}, limit={args.limit}")

    result = await cli.list_investigations(
        status=args.status,
        limit=args.limit,
        json_output=args.json
    )

    if args.verbose:
        logger.info(f"[VERBOSE] Found {result.get('total', 0)} investigations")

    return 0 if result.get("success") else 1


async def cmd_export_audit(args):
    """Handle export-audit command."""
    cli = DevRelAgentCLI(verbose=args.verbose)

    if args.verbose:
        logger.info(f"[VERBOSE] Exporting audit log to {args.output or 'default file'}")

    result = await cli.export_audit_log(args.output)

    if args.verbose:
        logger.info(f"[VERBOSE] Export result: {result.get('success')}")

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        if result.get("success"):
            print(f"\n[OK] Exported {result.get('events_exported', 0)} audit events to {result.get('output_file')}")
        else:
            print(f"\n[ERROR] Failed to export audit log: {result.get('error')}")

    return 0 if result.get("success") else 1


# ============== Grafana Commands ==============

async def cmd_grafana_test_connection(args):
    """Handle Grafana test-connection command."""
    from tools.grafana_tool import test_grafana_connection

    if args.verbose:
        logger.info("[VERBOSE] Testing Grafana connection...")

    result = await test_grafana_connection()

    if args.verbose:
        logger.info(f"[VERBOSE] Connection test result: {result.get('success')}")

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        if result.get("success"):
            print(f"\n[OK] Successfully connected to Grafana")
            print(f"   URL: {result.get('grafana_url')}")
            print(f"   Version: {result.get('grafana_version')}")
            datasources = result.get("datasources", [])
            print(f"   Datasources: {len(datasources)}")
            for ds in datasources:
                print(f"      - {ds.get('name')} ({ds.get('type')})")
        else:
            print(f"\n[ERROR] Failed to connect to Grafana: {result.get('error')}")
            if "troubleshooting" in result:
                print("\nTroubleshooting:")
                for key, value in result["troubleshooting"].items():
                    print(f"   {key}: {value}")

    return 0 if result.get("success") else 1


async def cmd_grafana_list_datasources(args):
    """Handle Grafana list-datasources command."""
    from tools.grafana_tool import list_grafana_datasources

    if args.verbose:
        logger.info("[VERBOSE] Fetching Grafana datasources...")

    result = await list_grafana_datasources()

    if args.verbose:
        logger.info(f"[VERBOSE] Found {result.get('total', 0)} datasources")

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        if result.get("success"):
            print(f"\n[OK] Available Grafana Datasources ({result.get('total', 0)}):\n")
            for ds in result.get("datasources", []):
                marker = " (default)" if ds.get("is_default") else ""
                print(f"   - {ds.get('name')}{marker}")
                print(f"     Type: {ds.get('type')}")
                print(f"     UID: {ds.get('uid')}")
                if ds.get("url"):
                    print(f"     URL: {ds.get('url')}")
                print()
        else:
            print(f"\n[ERROR] Failed to list datasources: {result.get('error')}")

    return 0 if result.get("success") else 1


async def cmd_grafana_create_dashboard(args):
    """Handle Grafana create-dashboard command."""
    from tools.grafana_tool import create_service_dashboard

    if args.verbose:
        logger.info(f"[VERBOSE] Creating dashboard for service: {args.service}")

    result = await create_service_dashboard(
        service_name=args.service,
        datasource_name=args.datasource,
        dashboard_title=args.title
    )

    if args.verbose:
        logger.info(f"[VERBOSE] Dashboard creation result: {result.get('success')}")

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        if result.get("success"):
            print(f"\n[OK] Dashboard created successfully!")
            print(f"   Service: {result.get('service_name')}")
            print(f"   Dashboard ID: {result.get('dashboard_id')}")
            print(f"   Dashboard URL: {result.get('dashboard_url')}")
            print(f"\n   Panels: {', '.join(result.get('panels', []))}")
            print("\nNext Steps:")
            for step in result.get("next_steps", []):
                print(f"   - {step}")
        else:
            print(f"\n[ERROR] Failed to create dashboard: {result.get('error')}")

    return 0 if result.get("success") else 1


async def cmd_grafana_list_dashboards(args):
    """Handle Grafana list-dashboards command."""
    from tools.grafana_tool import list_dashboards

    if args.verbose:
        logger.info(f"[VERBOSE] Listing dashboards with tag filter: {args.tag}")

    result = await list_dashboards(tag_filter=args.tag)

    if args.verbose:
        logger.info(f"[VERBOSE] Found {result.get('total', 0)} dashboards")

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        if result.get("success"):
            print(f"\n[OK] Grafana Dashboards ({result.get('total', 0)}):\n")
            for dash in result.get("dashboards", []):
                print(f"   - {dash.get('title')}")
                print(f"     UID: {dash.get('uid')}")
                print(f"     Tags: {', '.join(dash.get('tags', []))}")
                print(f"     URL: {dash.get('url')}")
                print()
        else:
            print(f"\n[ERROR] Failed to list dashboards: {result.get('error')}")

    return 0 if result.get("success") else 1


async def cmd_grafana_setup(args):
    """Handle Grafana setup command."""
    from tools.grafana_tool import get_setup_instructions

    if args.verbose:
        logger.info("[VERBOSE] Fetching Grafana setup instructions...")

    result = await get_setup_instructions()

    if args.verbose:
        logger.info("[VERBOSE] Setup instructions retrieved")

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        instructions = result.get("instructions", {})

        print("\n" + "="*70)
        print("GRAFANA INTEGRATION SETUP GUIDE")
        print("="*70 + "\n")

        for section_key, section_data in instructions.items():
            if section_key == "common_issues":
                continue

            if isinstance(section_data, dict) and "title" in section_data:
                print(f"\n{section_data['title']}")
                print("-" * len(section_data['title']))

                if "steps" in section_data:
                    for i, step in enumerate(section_data["steps"], 1):
                        print(f"   {i}. {step}")

                if section_data.get("example"):
                    print(f"\n   Example:\n{section_data['example']}")

                if section_data.get("note"):
                    print(f"\n   Note: {section_data['note']}")

        print("\n" + "="*70)
        print("COMMON ISSUES")
        print("="*70 + "\n")

        if "common_issues" in instructions:
            for issue, solution in instructions["common_issues"].items():
                print(f"   {issue}:")
                print(f"      {solution}\n")

    return 0


# ============== Main Entry Point ==============

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="DevRelAgent - Production-grade Developer Relations Agent CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Investigate an issue
  python cli.py investigate "Why is the API slow?"

  # Dry-run mode (no actions taken)
  python cli.py investigate "API errors" --dry-run

  # JSON output for automation
  python cli.py investigate "Database latency" --json

  # Auto-approve all actions (use with caution)
  python cli.py investigate "Create dashboard" --auto-approve

  # Verbose mode with detailed output
  python cli.py investigate "API errors" --verbose

  # Use specific session ID for continuity
  python cli.py investigate "Follow up on previous issue" --session sess_20260311_120000

  # Combined flags
  python cli.py investigate "Check logs" --dry-run --verbose --json

  # Get agent status
  python cli.py status

  # List all investigations
  python cli.py list-investigations

  # Export audit log
  python cli.py export-audit --output audit.json

  # Grafana: Test connection
  python cli.py grafana test-connection

  # Grafana: Create dashboard for a service
  python cli.py grafana create-dashboard --service my-api

  # Grafana: Show setup instructions
  python cli.py grafana setup
        """
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format"
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output with detailed information"
    )

    parser.add_argument(
        "--session",
        type=str,
        default=None,
        help="Specify session ID for investigation continuity"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Investigate command
    inv_parser = subparsers.add_parser("investigate", help="Run an investigation")
    inv_parser.add_argument("query", help="Investigation query")
    inv_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry-run mode (no write operations)"
    )
    inv_parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Auto-approve all actions (use with caution)"
    )
    inv_parser.add_argument(
        "--no-save",
        action="store_true",
        help="Don't save investigation"
    )
    inv_parser.add_argument(
        "--session",
        type=str,
        default=None,
        help="Session ID for investigation continuity (auto-generated if not provided)"
    )

    # Status command
    status_parser = subparsers.add_parser("status", help="Get agent status")

    # List investigations command
    list_parser = subparsers.add_parser("list-investigations", help="List investigations")
    list_parser.add_argument(
        "--status",
        help="Filter by status"
    )
    list_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number to return (default: 20)"
    )

    # Export audit command
    export_parser = subparsers.add_parser("export-audit", help="Export audit log")
    export_parser.add_argument(
        "--output",
        help="Output file path"
    )

    # Grafana commands
    grafana_parser = subparsers.add_parser("grafana", help="Grafana integration commands")
    grafana_subparsers = grafana_parser.add_subparsers(dest="grafana_command", help="Grafana commands")

    # Grafana test-connection
    grafana_test_parser = grafana_subparsers.add_parser("test-connection", help="Test Grafana connection")

    # Grafana list-datasources
    grafana_list_ds_parser = grafana_subparsers.add_parser("list-datasources", help="List Grafana datasources")

    # Grafana create-dashboard
    grafana_create_parser = grafana_subparsers.add_parser("create-dashboard", help="Create Grafana dashboard for a service")
    grafana_create_parser.add_argument("--service", required=True, help="Service name")
    grafana_create_parser.add_argument("--datasource", help="Datasource name (default: GRAFANA_DEFAULT_DATASOURCE)")
    grafana_create_parser.add_argument("--title", help="Custom dashboard title")

    # Grafana list-dashboards
    grafana_list_dash_parser = grafana_subparsers.add_parser("list-dashboards", help="List all Grafana dashboards")
    grafana_list_dash_parser.add_argument("--tag", help="Filter by tag")

    # Grafana setup
    grafana_setup_parser = grafana_subparsers.add_parser("setup", help="Show Grafana setup instructions")

    args = parser.parse_args()

    # Configure logging
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Run command
    if args.command == "investigate":
        return asyncio.run(cmd_investigate(args))
    elif args.command == "status":
        return asyncio.run(cmd_status(args))
    elif args.command == "list-investigations":
        return asyncio.run(cmd_list_investigations(args))
    elif args.command == "export-audit":
        return asyncio.run(cmd_export_audit(args))
    elif args.command == "grafana":
        if args.grafana_command == "test-connection":
            return asyncio.run(cmd_grafana_test_connection(args))
        elif args.grafana_command == "list-datasources":
            return asyncio.run(cmd_grafana_list_datasources(args))
        elif args.grafana_command == "create-dashboard":
            return asyncio.run(cmd_grafana_create_dashboard(args))
        elif args.grafana_command == "list-dashboards":
            return asyncio.run(cmd_grafana_list_dashboards(args))
        elif args.grafana_command == "setup":
            return asyncio.run(cmd_grafana_setup(args))
        else:
            print("Available Grafana commands:")
            print("   test-connection      - Test connection to Grafana")
            print("   list-datasources     - List all datasources")
            print("   create-dashboard     - Create dashboard for a service")
            print("   list-dashboards      - List all dashboards")
            print("   setup                - Show setup instructions")
            return 1
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
