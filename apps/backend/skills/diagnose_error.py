"""
DiagnoseErrorSkill — Multi-step error diagnosis

Chains: KeDB check → ClickHouse logs → Code search → Summary
"""

from typing import Dict, Any, Optional
import logging
from .base import Skill, SkillResult
from tools.registry import get_registry

logger = logging.getLogger(__name__)


class DiagnoseErrorSkill(Skill):
    """Skill for diagnosing errors through multi-step analysis."""
    
    def __init__(self):
        super().__init__(
            name="diagnose_error",
            description="Diagnose errors by checking KeDB, querying logs, searching code, and providing summary",
            required_tools=["kedb_lookup", "clickhouse_query", "code_search"]
        )
    
    async def execute(self, context: Dict[str, Any], **kwargs) -> SkillResult:
        """
        Execute error diagnosis workflow.
        
        Args:
            context: Execution context with tool registry, session info, etc.
            error_description: Description of the error to diagnose
            service_name: Optional service name to focus search
            time_range: Optional time range for log search
        """
        self.clear_steps()
        
        error_description = kwargs.get('error_description', '')
        service_name = kwargs.get('service_name', '')
        time_range = kwargs.get('time_range', '1h')
        
        if not error_description:
            return SkillResult(
                success=False,
                result=None,
                steps=self.steps,
                error="Error description is required"
            )
        
        try:
            registry = context.get('tool_registry') or get_registry()
            
            # Step 1: Check KeDB for known errors
            kedb_result = await self._check_kedb(registry, error_description)
            
            # If we found a known solution, return it
            if kedb_result and kedb_result.get('found_solution'):
                self.log_step("KeDB Check", "Found known solution")
                return SkillResult(
                    success=True,
                    result={
                        "diagnosis": "Known Error",
                        "solution": kedb_result.get('solution'),
                        "confidence": "high",
                        "source": "KeDB"
                    },
                    steps=self.steps
                )
            
            # Step 2: Query ClickHouse logs for recent errors
            log_result = await self._query_logs(registry, error_description, service_name, time_range)
            
            # Step 3: Search code for related functions/files
            code_result = await self._search_code(registry, error_description, log_result)
            
            # Step 4: Synthesize findings
            diagnosis = await self._synthesize_diagnosis(
                error_description, kedb_result, log_result, code_result
            )
            
            return SkillResult(
                success=True,
                result=diagnosis,
                steps=self.steps,
                metadata={
                    "kedb_checked": bool(kedb_result),
                    "logs_found": bool(log_result),
                    "code_found": bool(code_result)
                }
            )
            
        except Exception as e:
            logger.error(f"Error in DiagnoseErrorSkill: {e}")
            return SkillResult(
                success=False,
                result=None,
                steps=self.steps,
                error=str(e)
            )
    
    async def _check_kedb(self, registry, error_description: str) -> Optional[Dict[str, Any]]:
        """Check KeDB for known errors."""
        try:
            kedb_tool = registry.get("kedb_lookup")
            if not kedb_tool:
                self.log_step("KeDB Check", "KeDB tool not available")
                return None
            
            result = await kedb_tool.execute(query=error_description)
            self.log_step("KeDB Check", f"Searched for similar errors: {error_description[:50]}...")
            
            if result.success and result.result:
                return {
                    "found_solution": True,
                    "solution": result.result.get('solution'),
                    "similarity": result.result.get('similarity', 0)
                }
            
            return {"found_solution": False}
            
        except Exception as e:
            self.log_step("KeDB Check", f"Error: {e}")
            return None
    
    async def _query_logs(self, registry, error_description: str, service_name: str, time_range: str) -> Optional[Dict[str, Any]]:
        """Query ClickHouse logs for error patterns."""
        try:
            ch_tool = registry.get("clickhouse_query")
            if not ch_tool:
                self.log_step("Log Query", "ClickHouse tool not available")
                return None
            
            # Build natural language query for logs
            query_parts = [f"Show recent errors"]
            if service_name:
                query_parts.append(f"from service {service_name}")
            if "authentication" in error_description.lower() or "auth" in error_description.lower():
                query_parts.append("related to authentication")
            elif "database" in error_description.lower() or "sql" in error_description.lower():
                query_parts.append("related to database")
            
            query_parts.append(f"in the last {time_range}")
            
            natural_query = " ".join(query_parts)
            
            result = await ch_tool.execute(natural_query=natural_query)
            self.log_step("Log Query", f"Queried logs: {natural_query}")
            
            if result.success and result.result:
                return {
                    "logs_found": True,
                    "error_count": result.result.get('row_count', 0),
                    "sample_errors": result.result.get('data', [])[:5],  # Top 5 errors
                    "sql_executed": result.result.get('sql_executed')
                }
            
            return {"logs_found": False}
            
        except Exception as e:
            self.log_step("Log Query", f"Error: {e}")
            return None
    
    async def _search_code(self, registry, error_description: str, log_result: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Search code for related functions and files."""
        try:
            code_tool = registry.get("code_search")
            if not code_tool:
                self.log_step("Code Search", "Code search tool not available")
                return None
            
            # Extract function names or error signatures from logs
            search_terms = [error_description]
            
            if log_result and log_result.get('sample_errors'):
                for error in log_result['sample_errors']:
                    if isinstance(error, dict) and 'message' in error:
                        # Extract potential function names from error messages
                        message = error['message']
                        if 'function' in message.lower():
                            search_terms.append(message)
            
            # Search for the most relevant term
            search_term = search_terms[0]  # Start with the original description
            
            result = await code_tool.execute(query=search_term)
            self.log_step("Code Search", f"Searched code for: {search_term[:50]}...")
            
            if result.success and result.result:
                return {
                    "code_found": True,
                    "files": result.result.get('files', [])[:3],  # Top 3 files
                    "functions": result.result.get('functions', [])[:5]  # Top 5 functions
                }
            
            return {"code_found": False}
            
        except Exception as e:
            self.log_step("Code Search", f"Error: {e}")
            return None
    
    async def _synthesize_diagnosis(
        self, 
        error_description: str,
        kedb_result: Optional[Dict[str, Any]],
        log_result: Optional[Dict[str, Any]],
        code_result: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Synthesize findings into a comprehensive diagnosis."""
        
        diagnosis = {
            "error_description": error_description,
            "diagnosis_type": "multi_step_analysis",
            "confidence": "medium",
            "findings": {},
            "recommendations": [],
            "next_steps": []
        }
        
        # Analyze KeDB results
        if kedb_result and kedb_result.get('found_solution'):
            diagnosis["confidence"] = "high"
            diagnosis["findings"]["kedb"] = "Similar error found in knowledge base"
            diagnosis["recommendations"].append("Apply known solution from KeDB")
        else:
            diagnosis["findings"]["kedb"] = "No similar errors found in knowledge base"
        
        # Analyze log results
        if log_result and log_result.get('logs_found'):
            error_count = log_result.get('error_count', 0)
            diagnosis["findings"]["logs"] = f"Found {error_count} related log entries"
            
            if error_count > 10:
                diagnosis["recommendations"].append("High error frequency detected - investigate immediately")
                diagnosis["confidence"] = "high"
            elif error_count > 0:
                diagnosis["recommendations"].append("Review recent error patterns")
        else:
            diagnosis["findings"]["logs"] = "No recent log entries found"
            diagnosis["next_steps"].append("Check if logging is properly configured")
        
        # Analyze code results
        if code_result and code_result.get('code_found'):
            files = code_result.get('files', [])
            functions = code_result.get('functions', [])
            
            diagnosis["findings"]["code"] = f"Found {len(files)} related files and {len(functions)} functions"
            
            if files:
                diagnosis["next_steps"].append(f"Review files: {', '.join([f['name'] for f in files[:2]])}")
            if functions:
                diagnosis["next_steps"].append(f"Check functions: {', '.join([f['name'] for f in functions[:2]])}")
        else:
            diagnosis["findings"]["code"] = "No related code found"
            diagnosis["next_steps"].append("Verify error description and search terms")
        
        # General recommendations
        if not diagnosis["recommendations"]:
            diagnosis["recommendations"].append("Monitor error patterns and check system health")
        
        if not diagnosis["next_steps"]:
            diagnosis["next_steps"].append("Gather more specific error details")
        
        self.log_step("Synthesis", f"Generated diagnosis with {diagnosis['confidence']} confidence")
        
        return diagnosis