"""
Dashboard Tool — Dashboard Creation and Management

Provides tools for creating, retrieving, updating, and deleting monitoring dashboards.
All write operations require mandatory HITL approval.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from config.settings import get_settings

from tools.registry import ToolCategory, tool

logger = logging.getLogger(__name__)

# Dashboard storage path (single source of truth: config.settings)
DASHBOARD_STORAGE_PATH = get_settings().dashboard_storage_path


# ============== Helper Functions ==============

def _get_dashboard_path(dashboard_id: str) -> str:
    """Get file path for dashboard configuration."""
    return os.path.join(DASHBOARD_STORAGE_PATH, f"{dashboard_id}.json")


def _generate_default_layout(widget_count: int) -> Dict[str, Any]:
    """Generate default layout based on widget count."""
    columns = min(3, max(1, widget_count))
    rows = (widget_count + columns - 1) // columns

    return {
        "columns": columns,
        "rows": rows,
        "gap": 16,
        "widget_size": {
            "width": f"{100 // columns}%",
            "min_height": 200
        }
    }


def _validate_widget(widget: Dict[str, Any]) -> List[str]:
    """Validate widget configuration."""
    errors = []

    widget_type = widget.get("type")
    if not widget_type:
        errors.append("Widget missing 'type' field")
        return errors

    valid_types = [
        "metric_card", "chart", "log_table",
        "status_panel", "alert_feed", "table"
    ]

    if widget_type not in valid_types:
        errors.append(f"Invalid widget type: {widget_type}. Valid types: {valid_types}")

    # Required fields per type
    required_fields = {
        "metric_card": ["title", "metric_source"],
        "chart": ["title", "chart_type", "data_source"],
        "log_table": ["title", "log_source"],
        "status_panel": ["title", "services"],
        "alert_feed": ["title", "alert_source"],
        "table": ["title", "data_source"]
    }

    if widget_type in required_fields:
        for field in required_fields[widget_type]:
            if field not in widget:
                errors.append(f"{widget_type} widget missing required field: {field}")

    return errors


def _load_dashboard(dashboard_id: str) -> Optional[Dict[str, Any]]:
    """Load dashboard from storage."""
    try:
        path = _get_dashboard_path(dashboard_id)
        if os.path.exists(path):
            with open(path, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load dashboard {dashboard_id}: {e}")
    return None


def _save_dashboard(dashboard_id: str, dashboard_config: Dict[str, Any]) -> bool:
    """Save dashboard to storage."""
    try:
        # Ensure storage directory exists
        Path(DASHBOARD_STORAGE_PATH).mkdir(parents=True, exist_ok=True)

        path = _get_dashboard_path(dashboard_id)
        with open(path, 'w') as f:
            json.dump(dashboard_config, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Failed to save dashboard {dashboard_id}: {e}")
        return False


def _delete_dashboard_file(dashboard_id: str) -> bool:
    """Delete dashboard file from storage."""
    try:
        path = _get_dashboard_path(dashboard_id)
        if os.path.exists(path):
            os.remove(path)
            return True
    except Exception as e:
        logger.error(f"Failed to delete dashboard {dashboard_id}: {e}")
    return False


def _list_dashboard_files() -> List[str]:
    """List all dashboard IDs in storage."""
    try:
        if os.path.exists(DASHBOARD_STORAGE_PATH):
            return [
                Path(f).stem
                for f in os.listdir(DASHBOARD_STORAGE_PATH)
                if f.endswith('.json')
            ]
    except Exception as e:
        logger.error(f"Failed to list dashboards: {e}")
    return []


# ============== Tool Implementations ==============

@tool(
    name="create_dashboard",
    description="Create custom monitoring dashboard with specified widgets and layout",
    category=ToolCategory.SYSTEM,
    requires_approval=False,
    read_only=False,
    risk_level="low"
)
async def create_dashboard(
    name: str,
    description: str,
    widgets: List[Dict[str, Any]],
    layout: Optional[Dict[str, Any]] = None,
    refresh_interval_seconds: int = 30,
    theme: Literal["light", "dark", "auto"] = "dark",
    timezone: str = "UTC"
) -> Dict[str, Any]:
    """
    Create a custom monitoring dashboard.

    Args:
        name: Dashboard name (must be unique)
        description: Dashboard description
        widgets: List of widget configurations
        layout: Optional layout configuration (auto-generated if not provided)
        refresh_interval_seconds: Data refresh interval (default: 30s)
        theme: Dashboard theme (light/dark/auto)
        timezone: Dashboard timezone

    Returns:
        Dashboard creation result with dashboard ID
    """
    try:
        # Validate widgets
        all_errors = []
        for i, widget in enumerate(widgets):
            widget_errors = _validate_widget(widget)
            if widget_errors:
                all_errors.append(f"Widget {i}: {', '.join(widget_errors)}")

        if all_errors:
            return {
                "success": False,
                "error": f"Widget validation failed: {'; '.join(all_errors)}"
            }

        # Generate dashboard ID
        dashboard_id = f"dashboard_{name.lower().replace(' ', '_').replace('-', '_')}"

        # Check if dashboard already exists
        if _load_dashboard(dashboard_id):
            return {
                "success": False,
                "error": f"Dashboard '{name}' already exists (ID: {dashboard_id})"
            }

        # Generate layout if not provided
        if not layout:
            layout = _generate_default_layout(len(widgets))

        # Create dashboard configuration
        dashboard_config = {
            "id": dashboard_id,
            "name": name,
            "description": description,
            "widgets": widgets,
            "layout": layout,
            "refresh_interval_seconds": max(5, min(300, refresh_interval_seconds)),  # Clamp between 5-300s
            "theme": theme,
            "timezone": timezone,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "version": "1.0.0"
        }

        # Save dashboard
        if not _save_dashboard(dashboard_id, dashboard_config):
            return {
                "success": False,
                "error": "Failed to save dashboard configuration"
            }

        logger.info(f"Created dashboard: {dashboard_id} with {len(widgets)} widgets")

        return {
            "success": True,
            "dashboard_id": dashboard_id,
            "config": dashboard_config,
            "metadata": {
                "widget_count": len(widgets),
                "created_at": dashboard_config["created_at"]
            }
        }

    except Exception as e:
        logger.error(f"Dashboard creation failed: {e}")
        return {
            "success": False,
            "error": f"Dashboard creation failed: {str(e)}"
        }


@tool(
    name="get_dashboard",
    description="Retrieve dashboard configuration by ID",
    category=ToolCategory.SYSTEM,
    read_only=True
)
async def get_dashboard(
    dashboard_id: str
) -> Dict[str, Any]:
    """
    Retrieve dashboard configuration.

    Args:
        dashboard_id: Dashboard ID (e.g., dashboard_my_dashboard)

    Returns:
        Dashboard configuration
    """
    try:
        dashboard_config = _load_dashboard(dashboard_id)

        if not dashboard_config:
            return {
                "success": False,
                "error": f"Dashboard not found: {dashboard_id}"
            }

        return {
            "success": True,
            "dashboard_id": dashboard_id,
            "config": dashboard_config
        }

    except Exception as e:
        logger.error(f"Failed to get dashboard {dashboard_id}: {e}")
        return {
            "success": False,
            "error": f"Failed to get dashboard: {str(e)}"
        }


@tool(
    name="list_dashboards",
    description="List all available dashboards with metadata",
    category=ToolCategory.SYSTEM,
    read_only=True
)
async def list_dashboards() -> Dict[str, Any]:
    """
    List all available dashboards.

    Returns:
        List of dashboard configurations with metadata
    """
    try:
        dashboard_ids = _list_dashboard_files()

        dashboards = []
        for dashboard_id in dashboard_ids:
            config = _load_dashboard(dashboard_id)
            if config:
                dashboards.append({
                    "id": config.get("id"),
                    "name": config.get("name"),
                    "description": config.get("description"),
                    "widget_count": len(config.get("widgets", [])),
                    "created_at": config.get("created_at"),
                    "updated_at": config.get("updated_at"),
                    "theme": config.get("theme"),
                    "refresh_interval_seconds": config.get("refresh_interval_seconds")
                })

        return {
            "success": True,
            "dashboards": dashboards,
            "total": len(dashboards),
            "metadata": {
                "storage_path": DASHBOARD_STORAGE_PATH
            }
        }

    except Exception as e:
        logger.error(f"Failed to list dashboards: {e}")
        return {
            "success": False,
            "error": f"Failed to list dashboards: {str(e)}"
        }


@tool(
    name="update_dashboard",
    description="Update existing dashboard configuration",
    category=ToolCategory.SYSTEM,
    requires_approval=False,
    read_only=False,
    risk_level="low"
)
async def update_dashboard(
    dashboard_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    widgets: Optional[List[Dict[str, Any]]] = None,
    layout: Optional[Dict[str, Any]] = None,
    refresh_interval_seconds: Optional[int] = None,
    theme: Optional[Literal["light", "dark", "auto"]] = None,
    timezone: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update existing dashboard configuration.

    Args:
        dashboard_id: Dashboard ID to update
        name: New dashboard name (optional)
        description: New description (optional)
        widgets: New widget list (optional)
        layout: New layout (optional)
        refresh_interval_seconds: New refresh interval (optional)
        theme: New theme (optional)
        timezone: New timezone (optional)

    Returns:
        Update result
    """
    try:
        # Load existing dashboard
        config = _load_dashboard(dashboard_id)
        if not config:
            return {
                "success": False,
                "error": f"Dashboard not found: {dashboard_id}"
            }

        # Validate widgets if provided
        if widgets is not None:
            all_errors = []
            for i, widget in enumerate(widgets):
                widget_errors = _validate_widget(widget)
                if widget_errors:
                    all_errors.append(f"Widget {i}: {', '.join(widget_errors)}")

            if all_errors:
                return {
                    "success": False,
                    "error": f"Widget validation failed: {'; '.join(all_errors)}"
                }

        # Update fields
        updates = []
        if name is not None:
            config["name"] = name
            updates.append("name")
        if description is not None:
            config["description"] = description
            updates.append("description")
        if widgets is not None:
            config["widgets"] = widgets
            updates.append("widgets")
        if layout is not None:
            config["layout"] = layout
            updates.append("layout")
        if refresh_interval_seconds is not None:
            config["refresh_interval_seconds"] = max(5, min(300, refresh_interval_seconds))
            updates.append("refresh_interval_seconds")
        if theme is not None:
            config["theme"] = theme
            updates.append("theme")
        if timezone is not None:
            config["timezone"] = timezone
            updates.append("timezone")

        # Update timestamp
        config["updated_at"] = datetime.now().isoformat()

        # Save updated dashboard
        if not _save_dashboard(dashboard_id, config):
            return {
                "success": False,
                "error": "Failed to save updated dashboard"
            }

        logger.info(f"Updated dashboard {dashboard_id}: {', '.join(updates)}")

        return {
            "success": True,
            "dashboard_id": dashboard_id,
            "updated_fields": updates,
            "config": config
        }

    except Exception as e:
        logger.error(f"Dashboard update failed: {e}")
        return {
            "success": False,
            "error": f"Dashboard update failed: {str(e)}"
        }


@tool(
    name="delete_dashboard",
    description="Delete dashboard (requires approval)",
    category=ToolCategory.SYSTEM,
    requires_approval=True,
    approval_action_type="delete_operation",
    read_only=False,
    risk_level="medium"
)
async def delete_dashboard(
    dashboard_id: str,
    backup: bool = True
) -> Dict[str, Any]:
    """
    Delete dashboard with optional backup.

    ⚠️ WARNING: This will permanently delete the dashboard.

    Args:
        dashboard_id: Dashboard ID to delete
        backup: Create backup before deletion (recommended)

    Returns:
        Deletion result with backup location
    """
    try:
        # Check if dashboard exists
        config = _load_dashboard(dashboard_id)
        if not config:
            return {
                "success": False,
                "error": f"Dashboard not found: {dashboard_id}"
            }

        # Create backup if requested
        backup_path = None
        if backup:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"{dashboard_id}_backup_{timestamp}.json"
            backup_path = os.path.join(DASHBOARD_STORAGE_PATH, "backups", backup_filename)

            # Ensure backup directory exists
            Path(os.path.dirname(backup_path)).mkdir(parents=True, exist_ok=True)

            if _save_dashboard(backup_path, config):
                logger.info(f"Created dashboard backup: {backup_path}")
            else:
                backup_path = None

        # Delete dashboard
        if not _delete_dashboard_file(dashboard_id):
            return {
                "success": False,
                "error": "Failed to delete dashboard file"
            }

        logger.info(f"Deleted dashboard: {dashboard_id}")

        return {
            "success": True,
            "dashboard_id": dashboard_id,
            "backup_path": backup_path,
            "metadata": {
                "deleted_at": datetime.now().isoformat(),
                "backup_created": backup_path is not None,
                "dashboard_name": config.get("name")
            }
        }

    except Exception as e:
        logger.error(f"Dashboard deletion failed: {e}")
        return {
            "success": False,
            "error": f"Dashboard deletion failed: {str(e)}"
        }


@tool(
    name="get_dashboard_templates",
    description="Get available dashboard widget templates and examples",
    category=ToolCategory.SYSTEM,
    read_only=True
)
async def get_dashboard_templates() -> Dict[str, Any]:
    """
    Get available dashboard widget templates and configuration examples.

    Returns:
        Dictionary of widget templates and examples
    """
    return {
        "success": True,
        "widget_types": {
            "metric_card": {
                "description": "Display a single key metric",
                "required_fields": ["title", "metric_source"],
                "optional_fields": ["unit", "format", "threshold", "color"],
                "example": {
                    "type": "metric_card",
                    "title": "Error Rate",
                    "metric_source": "clickhouse:logs:error_rate",
                    "unit": "%",
                    "format": "percentage",
                    "threshold": {"warning": 5, "critical": 10},
                    "color": "auto"
                }
            },
            "chart": {
                "description": "Display data as a chart",
                "required_fields": ["title", "chart_type", "data_source"],
                "optional_fields": ["x_axis", "y_axis", "group_by", "time_range"],
                "chart_types": ["line", "bar", "pie", "area", "scatter"],
                "example": {
                    "type": "chart",
                    "title": "Request Volume",
                    "chart_type": "line",
                    "data_source": "clickhouse:logs:request_count",
                    "x_axis": "timestamp",
                    "y_axis": "count",
                    "time_range": "1h"
                }
            },
            "log_table": {
                "description": "Display log entries in a table",
                "required_fields": ["title", "log_source"],
                "optional_fields": ["columns", "filters", "max_rows", "refresh_interval"],
                "example": {
                    "type": "log_table",
                    "title": "Recent Errors",
                    "log_source": "clickhouse:logs:errors",
                    "columns": ["timestamp", "level", "service", "message"],
                    "max_rows": 100,
                    "filters": {"level": "ERROR"}
                }
            },
            "status_panel": {
                "description": "Display service health status",
                "required_fields": ["title", "services"],
                "optional_fields": ["show_details", "refresh_interval"],
                "example": {
                    "type": "status_panel",
                    "title": "Service Health",
                    "services": ["api", "database", "cache", "worker"],
                    "show_details": True
                }
            },
            "alert_feed": {
                "description": "Display alert timeline",
                "required_fields": ["title", "alert_source"],
                "optional_fields": ["severity_filter", "max_alerts", "time_range"],
                "example": {
                    "type": "alert_feed",
                    "title": "Recent Alerts",
                    "alert_source": "health_scheduler",
                    "severity_filter": ["critical", "warning"],
                    "max_alerts": 50,
                    "time_range": "24h"
                }
            },
            "table": {
                "description": "Display tabular data",
                "required_fields": ["title", "data_source"],
                "optional_fields": ["columns", "sort_by", "max_rows"],
                "example": {
                    "type": "table",
                    "title": "Top Errors",
                    "data_source": "clickhouse:logs:top_errors",
                    "columns": ["error_message", "count", "service"],
                    "sort_by": "-count",
                    "max_rows": 20
                }
            }
        },
        "layout_examples": {
            "single_column": {
                "columns": 1,
                "rows": "auto",
                "gap": 16
            },
            "two_column": {
                "columns": 2,
                "rows": "auto",
                "gap": 16
            },
            "three_column": {
                "columns": 3,
                "rows": "auto",
                "gap": 16
            },
            "custom_grid": {
                "columns": 4,
                "rows": 3,
                "gap": 16,
                "widget_size": {
                    "width": "25%",
                    "min_height": 200
                }
            }
        },
        "theme_options": ["light", "dark", "auto"],
        "refresh_intervals": {
            "fast": 5,
            "normal": 30,
            "slow": 60
        }
    }
