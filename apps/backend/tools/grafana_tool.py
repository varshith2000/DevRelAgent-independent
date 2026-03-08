"""
Grafana Integration Tool — Real Grafana Dashboard Creation

This tool provides ACTUAL Grafana dashboard creation and management.
Users can create real Grafana dashboards that visualize their service data.

Requirements:
- Grafana instance running (http://localhost:3000 or custom URL)
- Grafana API token with admin or editor permissions
- Datasource configured in Grafana (ClickHouse, Prometheus, etc.)

Usage:
1. Set GRAFANA_URL and GRAFANA_API_TOKEN environment variables
2. Use CLI: python cli.py grafana create-dashboard --service api
3. Dashboard will be created in your Grafana instance
"""

import json
import logging
import os
from typing import Dict, Any, List, Optional, Literal
from datetime import datetime, timedelta
import httpx

from tools.registry import tool, ToolCategory

logger = logging.getLogger(__name__)

# Grafana Configuration
GRAFANA_URL = os.getenv("GRAFANA_URL", "http://localhost:3000")
GRAFANA_API_TOKEN = os.getenv("GRAFANA_API_TOKEN", "")
GRAFANA_DEFAULT_DATASOURCE = os.getenv("GRAFANA_DEFAULT_DATASOURCE", "ClickHouse")

# Headers for Grafana API
GRAFANA_HEADERS = {
    "Authorization": f"Bearer {GRAFANA_API_TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json"
}


# ============== Helper Functions ==============

def _grafana_request(
    method: str,
    endpoint: str,
    data: Optional[Dict[str, Any]] = None,
    timeout: float = 30.0
) -> Dict[str, Any]:
    """
    Make request to Grafana API.

    Args:
        method: HTTP method (GET, POST, PUT, DELETE)
        endpoint: API endpoint path
        data: Request body data
        timeout: Request timeout

    Returns:
        Response dictionary
    """
    if not GRAFANA_API_TOKEN:
        return {
            "success": False,
            "error": "GRAFANA_API_TOKEN not set. Please set environment variable."
        }

    url = f"{GRAFANA_URL}/api{endpoint}"

    try:
        async def _make_request():
            async with httpx.AsyncClient(timeout=timeout) as client:
                if method.upper() == "GET":
                    response = await client.get(url, headers=GRAFANA_HEADERS, params=data)
                elif method.upper() == "POST":
                    response = await client.post(url, headers=GRAFANA_HEADERS, json=data)
                elif method.upper() == "PUT":
                    response = await client.put(url, headers=GRAFANA_HEADERS, json=data)
                elif method.upper() == "DELETE":
                    response = await client.delete(url, headers=GRAFANA_HEADERS)
                else:
                    return {"success": False, "error": f"Invalid method: {method}"}

                if response.status_code in [200, 201, 202]:
                    try:
                        return {"success": True, "data": response.json(), "status": response.status_code}
                    except json.JSONDecodeError:
                        return {"success": True, "data": response.text, "status": response.status_code}
                else:
                    return {
                        "success": False,
                        "error": f"Grafana API error: {response.status_code} - {response.text}",
                        "status": response.status_code
                    }

        import asyncio
        return asyncio.run(_make_request())

    except httpx.ConnectError:
        return {
            "success": False,
            "error": f"Cannot connect to Grafana at {GRAFANA_URL}. Ensure Grafana is running."
        }
    except Exception as e:
        logger.error(f"Grafana request failed: {e}")
        return {"success": False, "error": str(e)}


def _generate_dashboard_uid(service_name: str) -> str:
    """Generate unique dashboard UID for service."""
    return f"devrelagent-{service_name.lower().replace('_', '-').replace(' ', '-')}"


def _get_datasource_uid(datasource_name: str) -> Optional[str]:
    """
    Get datasource UID from Grafana.

    Args:
        datasource_name: Name of datasource in Grafana

    Returns:
        Datasource UID or None
    """
    result = _grafana_request("GET", "/datasources")

    if not result.get("success"):
        return None

    datasources = result.get("data", [])
    for ds in datasources:
        if ds.get("name") == datasource_name:
            return ds.get("uid")

    return None


# ============== Dashboard Templates ==============

def _create_error_rate_panel(
    service: str,
    datasource_uid: str,
    position: Dict[str, int]
) -> Dict[str, Any]:
    """Create error rate panel for dashboard."""
    return {
        "id": 1001,
        "title": f"Error Rate - {service}",
        "type": "timeseries",
        "gridPos": position,
        "options": {
            "legend": {"displayMode": "table", "placement": "bottom"},
            "tooltip": {"mode": "multi"}
        },
        "targets": [
            {
                "datasource": {"type": "grafana", "uid": datasource_uid},
                "expr": f'rate(logs_errors_total{{service="{service}"}}[5m]) * 100',
                "legendFormat": "Error Rate",
                "refId": "A"
            },
            {
                "datasource": {"type": "grafana", "uid": datasource_uid},
                "expr": f'rate(logs_requests_total{{service="{service}"}}[5m]) * 100',
                "legendFormat": "Request Rate",
                "refId": "B"
            }
        ]
    }


def _create_latency_panel(
    service: str,
    datasource_uid: str,
    position: Dict[str, int]
) -> Dict[str, Any]:
    """Create latency panel for dashboard."""
    return {
        "id": 1002,
        "title": f"Latency (P50, P95, P99) - {service}",
        "type": "timeseries",
        "gridPos": position,
        "options": {
            "legend": {"displayMode": "table", "placement": "bottom"},
            "tooltip": {"mode": "multi"}
        },
        "targets": [
            {
                "datasource": {"type": "grafana", "uid": datasource_uid},
                "expr": f'histogram_quantile(0.50, rate(http_request_duration_seconds_bucket{{service="{service}"}}[5m]))',
                "legendFormat": "P50",
                "refId": "A"
            },
            {
                "datasource": {"type": "grafana", "uid": datasource_uid},
                "expr": f'histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{{service="{service}"}}[5m]))',
                "legendFormat": "P95",
                "refId": "B"
            },
            {
                "datasource": {"type": "grafana", "uid": datasource_uid},
                "expr": f'histogram_quantile(0.99, rate(http_request_duration_seconds_bucket{{service="{service}"}}[5m]))',
                "legendFormat": "P99",
                "refId": "C"
            }
        ]
    }


def _create_requests_panel(
    service: str,
    datasource_uid: str,
    position: Dict[str, int]
) -> Dict[str, Any]:
    """Create requests per minute panel."""
    return {
        "id": 1003,
        "title": f"Requests Per Minute - {service}",
        "type": "timeseries",
        "gridPos": position,
        "options": {
            "legend": {"displayMode": "table", "placement": "bottom"}
        },
        "targets": [
            {
                "datasource": {"type": "grafana", "uid": datasource_uid},
                "expr": f'rate(logs_requests_total{{service="{service}"}}[1m]) * 60',
                "legendFormat": "Requests/min",
                "refId": "A"
            }
        ]
    }


def _create_top_errors_panel(
    service: str,
    datasource_uid: str,
    position: Dict[str, int]
) -> Dict[str, Any]:
    """Create top errors table panel."""
    return {
        "id": 1004,
        "title": f"Top Errors - {service}",
        "type": "table",
        "gridPos": position,
        "options": {
            "showHeader": True,
            "frameIndex": 0
        },
        "transformations": [
            {
                "id": "organize",
                "options": {
                    "excludeByName": {"Time": True},
                    "indexByName": {},
                    "renameByName": {}
                }
            }
        ],
        "targets": [
            {
                "datasource": {"type": "grafana", "uid": datasource_uid},
                "expr": f'topk(10, count by (error_message) (logs_errors_total{{service="{service}"}}))',
                "legendFormat": "{{error_message}}",
                "refId": "A",
                "format": "table"
            }
        ]
    }


def _create_availability_gauge(
    service: str,
    datasource_uid: str,
    position: Dict[str, int]
) -> Dict[str, Any]:
    """Create availability gauge panel."""
    return {
        "id": 1005,
        "title": f"Availability - {service}",
        "type": "stat",
        "gridPos": position,
        "options": {
            "graphMode": "area",
            "orientation": "auto",
            "reduceOptions": {
                "calcs": ["lastNotNull"],
                "fields": "",
                "values": False
            },
            "textMode": "auto"
        },
        "fieldConfig": {
            "defaults": {
                "unit": "percent",
                "min": 0,
                "max": 100,
                "thresholds": {
                    "mode": "absolute",
                    "steps": [
                        {"value": 0, "color": "red"},
                        {"value": 99, "color": "yellow"},
                        {"value": 99.9, "color": "green"}
                    ]
                }
            }
        },
        "targets": [
            {
                "datasource": {"type": "grafana", "uid": datasource_uid},
                "expr": f'(1 - (rate(logs_errors_total{{service="{service}"}}[5m]) / rate(logs_requests_total{{service="{service}"}}[5m]))) * 100',
                "legendFormat": "Availability",
                "refId": "A"
            }
        ]
    }


def _create_service_dashboard_json(
    service_name: str,
    datasource_uid: str,
    dashboard_title: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate complete Grafana dashboard JSON for a service.

    Args:
        service_name: Name of the service
        datasource_uid: Grafana datasource UID
        dashboard_title: Optional custom dashboard title

    Returns:
        Complete Grafana dashboard JSON
    """
    title = dashboard_title or f"{service_name} - DevRelAgent Dashboard"
    uid = _generate_dashboard_uid(service_name)

    return {
        "dashboard": {
            "title": title,
            "uid": uid,
            "tags": ["devrelagent", "service", service_name, "monitoring"],
            "timezone": "browser",
            "schemaVersion": 36,
            "version": 1,
            "refresh": "30s",
            "time": {
                "from": "now-1h",
                "to": "now"
            },
            "timepicker": {},
            "panels": [
                _create_availability_gauge(service_name, datasource_uid, {
                    "h": 8, "w": 6, "x": 0, "y": 0
                }),
                _create_requests_panel(service_name, datasource_uid, {
                    "h": 8, "w": 9, "x": 6, "y": 0
                }),
                _create_error_rate_panel(service_name, datasource_uid, {
                    "h": 8, "w": 9, "x": 15, "y": 0
                }),
                _create_latency_panel(service_name, datasource_uid, {
                    "h": 8, "w": 12, "x": 0, "y": 8
                }),
                _create_top_errors_panel(service_name, datasource_uid, {
                    "h": 8, "w": 12, "x": 12, "y": 8
                })
            ]
        },
        "overwrite": True
    }


def _create_multi_service_dashboard_json(
    service_names: List[str],
    datasource_uid: str,
    dashboard_title: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create dashboard comparing multiple services.

    Args:
        service_names: List of service names
        datasource_uid: Grafana datasource UID
        dashboard_title: Optional custom dashboard title

    Returns:
        Complete Grafana dashboard JSON
    """
    title = dashboard_title or "Multi-Service Overview"
    uid = _generate_dashboard_uid("multi-service")

    panels = []
    x_pos = 0
    y_pos = 0

    # Create panels for each service
    for service in service_names:
        panels.append(_create_error_rate_panel(service, datasource_uid, {
            "h": 6, "w": 12, "x": x_pos, "y": y_pos
        }))
        y_pos += 6
        if x_pos == 0:
            x_pos = 12
        else:
            x_pos = 0

    return {
        "dashboard": {
            "title": title,
            "uid": uid,
            "tags": ["devrelagent", "multi-service", "overview"],
            "timezone": "browser",
            "schemaVersion": 36,
            "version": 1,
            "refresh": "30s",
            "time": {
                "from": "now-6h",
                "to": "now"
            },
            "panels": panels
        },
        "overwrite": True
    }


# ============== Tool Implementations ==============

@tool(
    name="test_grafana_connection",
    description="Test connection to Grafana instance",
    category=ToolCategory.SYSTEM,
    read_only=True
)
async def test_grafana_connection() -> Dict[str, Any]:
    """
    Test connection to Grafana and return connection details.

    Returns:
        Connection status with Grafana version and available datasources
    """
    result = _grafana_request("GET", "/health")

    if not result.get("success"):
        return {
            "success": False,
            "error": result.get("error"),
            "troubleshooting": {
                "check_grafana_running": f"Ensure Grafana is running at {GRAFANA_URL}",
                "check_api_token": "Ensure GRAFANA_API_TOKEN environment variable is set",
                "test_connection": f"Try: curl -H \"Authorization: Bearer $GRAFANA_API_TOKEN\" {GRAFANA_URL}/api/health"
            }
        }

    # Get datasources
    datasources_result = _grafana_request("GET", "/datasources")

    return {
        "success": True,
        "grafana_url": GRAFANA_URL,
        "grafana_version": result.get("data", {}).get("version"),
        "database": result.get("data", {}).get("database"),
        "datasources": datasources_result.get("data", []) if datasources_result.get("success") else [],
        "message": "Successfully connected to Grafana"
    }


@tool(
    name="list_grafana_datasources",
    description="List all datasources configured in Grafana",
    category=ToolCategory.SYSTEM,
    read_only=True
)
async def list_grafana_datasources() -> Dict[str, Any]:
    """
    List all datasources available in Grafana.

    Returns:
        List of datasources with names, types, and UIDs
    """
    result = _grafana_request("GET", "/datasources")

    if not result.get("success"):
        return result

    datasources = result.get("data", [])

    return {
        "success": True,
        "datasources": [
            {
                "name": ds.get("name"),
                "type": ds.get("type"),
                "uid": ds.get("uid"),
                "url": ds.get("url"),
                "is_default": ds.get("isDefault")
            }
            for ds in datasources
        ],
        "total": len(datasources),
        "recommended_datasource": GRAFANA_DEFAULT_DATASOURCE
    }


@tool(
    name="create_service_dashboard",
    description="Create Grafana dashboard for a service with error rate, latency, availability metrics",
    category=ToolCategory.API,
    requires_approval=True,
    approval_action_type="grafana_dashboard",
    read_only=False,
    risk_level="low"
)
async def create_service_dashboard(
    service_name: str,
    datasource_name: Optional[str] = None,
    dashboard_title: Optional[str] = None,
    auto_provision: bool = False
) -> Dict[str, Any]:
    """
    Create a complete Grafana dashboard for monitoring a service.

    Dashboard includes:
    - Availability gauge (target: 99.9%)
    - Requests per minute
    - Error rate
    - Latency (P50, P95, P99)
    - Top errors table

    Args:
        service_name: Name of the service to monitor
        datasource_name: Grafana datasource name (default: GRAFANA_DEFAULT_DATASOURCE)
        dashboard_title: Custom dashboard title (optional)
        auto_provision: Auto-create datasource if not found (experimental)

    Returns:
        Dashboard creation result with URL
    """
    # Use default datasource if not specified
    datasource = datasource_name or GRAFANA_DEFAULT_DATASOURCE

    # Get datasource UID
    datasource_uid = _get_datasource_uid(datasource)

    if not datasource_uid:
        return {
            "success": False,
            "error": f"Datasource '{datasource}' not found in Grafana",
            "available_datasources": await list_grafana_datasources(),
            "solution": "Configure the datasource in Grafana UI or specify a different datasource_name"
        }

    # Generate dashboard JSON
    dashboard_json = _create_service_dashboard_json(
        service_name=service_name,
        datasource_uid=datasource_uid,
        dashboard_title=dashboard_title
    )

    # Create dashboard in Grafana
    result = _grafana_request("POST", "/dashboards/db", dashboard_json)

    if not result.get("success"):
        return result

    dashboard_data = result.get("data", {})
    dashboard_id = dashboard_data.get("id")
    dashboard_uid = dashboard_data.get("uid")
    dashboard_url = f"{GRAFANA_URL}/d/{dashboard_uid}"

    logger.info(f"Created Grafana dashboard for service '{service_name}': {dashboard_url}")

    return {
        "success": True,
        "service_name": service_name,
        "dashboard_id": dashboard_id,
        "dashboard_uid": dashboard_uid,
        "dashboard_url": dashboard_url,
        "datasource": datasource,
        "panels": ["Availability", "Requests/min", "Error Rate", "Latency", "Top Errors"],
        "next_steps": [
            f"View dashboard at: {dashboard_url}",
            "Panels will populate once your service sends metrics to the datasource"
        ]
    }


@tool(
    name="create_multi_service_dashboard",
    description="Create Grafana dashboard comparing multiple services",
    category=ToolCategory.API,
    requires_approval=True,
    approval_action_type="grafana_dashboard",
    read_only=False,
    risk_level="low"
)
async def create_multi_service_dashboard(
    service_names: List[str],
    datasource_name: Optional[str] = None,
    dashboard_title: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a dashboard comparing multiple services side-by-side.

    Args:
        service_names: List of service names to compare
        datasource_name: Grafana datasource name
        dashboard_title: Custom dashboard title

    Returns:
        Dashboard creation result
    """
    if not service_names or len(service_names) < 2:
        return {
            "success": False,
            "error": "At least 2 services required for comparison dashboard"
        }

    datasource = datasource_name or GRAFANA_DEFAULT_DATASOURCE
    datasource_uid = _get_datasource_uid(datasource)

    if not datasource_uid:
        return {
            "success": False,
            "error": f"Datasource '{datasource}' not found in Grafana"
        }

    dashboard_json = _create_multi_service_dashboard_json(
        service_names=service_names,
        datasource_uid=datasource_uid,
        dashboard_title=dashboard_title
    )

    result = _grafana_request("POST", "/dashboards/db", dashboard_json)

    if not result.get("success"):
        return result

    dashboard_data = result.get("data", {})
    dashboard_url = f"{GRAFANA_URL}/d/{dashboard_data.get('uid')}"

    logger.info(f"Created multi-service dashboard for {len(service_names)} services: {dashboard_url}")

    return {
        "success": True,
        "services": service_names,
        "dashboard_url": dashboard_url,
        "dashboard_id": dashboard_data.get("id")
    }


@tool(
    name="export_dashboard_json",
    description="Export Grafana dashboard as JSON file",
    category=ToolCategory.API,
    read_only=True
)
async def export_dashboard_json(
    dashboard_uid: str,
    output_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Export a dashboard from Grafana as JSON.

    Args:
        dashboard_uid: Dashboard UID to export
        output_path: Optional file path to save JSON (default: print to console)

    Returns:
        Dashboard JSON content
    """
    result = _grafana_request("GET", f"/dashboards/uid/{dashboard_uid}")

    if not result.get("success"):
        return result

    dashboard_data = result.get("data", {})
    dashboard_json = dashboard_data.get("dashboard", {})

    export_data = {
        "dashboard": dashboard_json,
        "exported_at": datetime.now().isoformat(),
        "version": dashboard_data.get("version")
    }

    # Save to file if path provided
    if output_path:
        try:
            with open(output_path, 'w') as f:
                json.dump(export_data, f, indent=2)
            logger.info(f"Exported dashboard to {output_path}")
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to save to {output_path}: {str(e)}",
                "dashboard_json": export_data
            }

    return {
        "success": True,
        "dashboard_json": export_data,
        "saved_to": output_path if output_path else None
    }


@tool(
    name="import_dashboard_json",
    description="Import Grafana dashboard from JSON file",
    category=ToolCategory.API,
    requires_approval=True,
    approval_action_type="grafana_dashboard",
    read_only=False,
    risk_level="low"
)
async def import_dashboard_json(
    json_path: str,
    overwrite: bool = False
) -> Dict[str, Any]:
    """
    Import a dashboard from JSON file into Grafana.

    Args:
        json_path: Path to dashboard JSON file
        overwrite: Overwrite existing dashboard if UID exists

    Returns:
        Import result with dashboard URL
    """
    try:
        with open(json_path, 'r') as f:
            dashboard_data = json.load(f)

        dashboard_json = {
            "dashboard": dashboard_data.get("dashboard"),
            "overwrite": overwrite
        }

        result = _grafana_request("POST", "/dashboards/db", dashboard_json)

        if not result.get("success"):
            return result

        dashboard_result = result.get("data", {})
        dashboard_url = f"{GRAFANA_URL}/d/{dashboard_result.get('uid')}"

        logger.info(f"Imported dashboard from {json_path}: {dashboard_url}")

        return {
            "success": True,
            "dashboard_url": dashboard_url,
            "dashboard_id": dashboard_result.get("id"),
            "dashboard_uid": dashboard_result.get("uid")
        }

    except FileNotFoundError:
        return {
            "success": False,
            "error": f"File not found: {json_path}"
        }
    except json.JSONDecodeError:
        return {
            "success": False,
            "error": f"Invalid JSON in file: {json_path}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to import dashboard: {str(e)}"
        }


@tool(
    name="list_dashboards",
    description="List all dashboards in Grafana",
    category=ToolCategory.SYSTEM,
    read_only=True
)
async def list_dashboards(
    tag_filter: Optional[str] = None
) -> Dict[str, Any]:
    """
    List all dashboards in Grafana.

    Args:
        tag_filter: Optional filter by tag (e.g., "devrelagent")

    Returns:
        List of dashboards with metadata
    """
    params = {}
    if tag_filter:
        params["tag"] = tag_filter

    result = _grafana_request("GET", "/search", params)

    if not result.get("success"):
        return result

    dashboards = result.get("data", [])

    return {
        "success": True,
        "dashboards": [
            {
                "title": d.get("title"),
                "uid": d.get("uid"),
                "id": d.get("id"),
                "tags": d.get("tags", []),
                "url": f"{GRAFANA_URL}{d.get('url')}"
            }
            for d in dashboards
        ],
        "total": len(dashboards),
        "filter": tag_filter
    }


@tool(
    name="delete_dashboard",
    description="Delete a dashboard from Grafana (requires approval)",
    category=ToolCategory.API,
    requires_approval=True,
    approval_action_type="delete_dashboard",
    read_only=False,
    risk_level="medium"
)
async def delete_dashboard(
    dashboard_uid: str
) -> Dict[str, Any]:
    """
    Delete a dashboard from Grafana.

    ⚠️ WARNING: This will permanently delete the dashboard.

    Args:
        dashboard_uid: Dashboard UID to delete

    Returns:
        Deletion result
    """
    result = _grafana_request("DELETE", f"/dashboards/uid/{dashboard_uid}")

    if not result.get("success"):
        return result

    logger.info(f"Deleted dashboard: {dashboard_uid}")

    return {
        "success": True,
        "message": f"Dashboard {dashboard_uid} deleted successfully"
    }


@tool(
    name="get_setup_instructions",
    description="Get setup instructions for Grafana integration",
    category=ToolCategory.SYSTEM,
    read_only=True
)
async def get_setup_instructions() -> Dict[str, Any]:
    """
    Get complete setup instructions for Grafana integration.

    Returns:
        Setup instructions with commands and configuration steps
    """
    return {
        "success": True,
        "instructions": {
            "prerequisites": [
                "Grafana installed and running (default: http://localhost:3000)",
                "Grafana API token with admin or editor permissions",
                "Datasource configured in Grafana (ClickHouse, Prometheus, etc.)"
            ],
            "step1_create_api_token": {
                "title": "1. Create Grafana API Token",
                "steps": [
                    "Open Grafana in browser (http://localhost:3000)",
                    "Go to Configuration → API Keys",
                    "Click 'Add API key'",
                    "Name: 'DevRelAgent'",
                    "Role: 'Admin' or 'Editor'",
                    "Time to live: '365 days' or 'Never expires'",
                    "Copy the generated token"
                ]
            },
            "step2_configure_datasource": {
                "title": "2. Configure Datasource in Grafana",
                "example": "For ClickHouse:",
                "steps": [
                    "Go to Configuration → Data sources",
                    "Click 'Add data source'",
                    "Select 'ClickHouse'",
                    "Name: 'ClickHouse'",
                    "Host: 'localhost:8123'",
                    "Database: 'logs'",
                    "Click 'Save & Test'"
                ],
                "note": "Replace with your actual datasource configuration"
            },
            "step3_set_environment_variables": {
                "title": "3. Set Environment Variables",
                "linux_mac": """
export GRAFANA_URL="http://localhost:3000"
export GRAFANA_API_TOKEN="your_token_here"
export GRAFANA_DEFAULT_DATASOURCE="ClickHouse"
                """,
                "windows": """
set GRAFANA_URL=http://localhost:3000
set GRAFANA_API_TOKEN=your_token_here
set GRAFANA_DEFAULT_DATASOURCE=ClickHouse
                """,
                "persistent": "Add to ~/.bashrc or ~/.zshrc for persistence"
            },
            "step4_test_connection": {
                "title": "4. Test Connection",
                "command": "python cli.py grafana test-connection",
                "expected_output": "Successfully connected to Grafana"
            },
            "step5_create_dashboard": {
                "title": "5. Create Dashboard",
                "command": "python cli.py grafana create-dashboard --service api",
                "expected_output": "Dashboard created with URL"
            },
            "common_issues": {
                "connection_refused": "Ensure Grafana is running at GRAFANA_URL",
                "unauthorized": "Check GRAFANA_API_TOKEN is valid and not expired",
                "datasource_not_found": "Configure datasource in Grafana UI first",
                "dashboard_empty": "Datasource must receive data before panels show metrics"
            },
            "example_workflow": {
                "title": "Complete Example Workflow",
                "steps": [
                    "1. Set environment variables (see step 3)",
                    "2. Test connection: python cli.py grafana test-connection",
                    "3. List datasources: python cli.py grafana list-datasources",
                    "4. Create dashboard: python cli.py grafana create-dashboard --service my-api",
                    "5. Open dashboard URL in browser",
                    "6. Your service data will appear in dashboard"
                ]
            }
        }
    }
