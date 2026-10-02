"""
Config Tool — System Configuration Generation and Management

Provides tools for generating, validating, and applying system configurations.
All write operations require mandatory HITL approval.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from config.settings import get_settings

from tools.registry import ToolCategory, tool

logger = logging.getLogger(__name__)

_settings = get_settings()


# ============== Configuration Templates ==============

def _generate_clickhouse_config(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Generate ClickHouse configuration."""
    return {
        "host": settings.get("host", _settings.clickhouse_host or "localhost"),
        "port": settings.get("port", _settings.clickhouse_port or 8123),
        "database": settings.get("database", _settings.clickhouse_database),
        "user": settings.get("user", _settings.clickhouse_user),
        "password": settings.get("password", _settings.clickhouse_password),
        "secure": settings.get("secure", _settings.clickhouse_secure),
        "connect_timeout": settings.get("connect_timeout", 10),
        "send_receive_timeout": settings.get("send_receive_timeout", 300),
        "compress": settings.get("compress", True),
        "settings": {
            "max_execution_time": settings.get("max_execution_time", 60),
            "max_rows_to_read": settings.get("max_rows_to_read", 1000000),
            "max_result_rows": settings.get("max_result_rows", 10000),
        }
    }


def _generate_github_config(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Generate GitHub configuration."""
    return {
        "api_base": settings.get("api_base", "https://api.github.com"),
        "token": settings.get("token", _settings.github_token or ""),
        "default_branch": settings.get("default_branch", "main"),
        "repositories": settings.get("repositories", []),
        "webhook_secret": settings.get("webhook_secret", ""),
        "rate_limit": {
            "enabled": settings.get("rate_limit_enabled", True),
            "requests_per_hour": settings.get("requests_per_hour", 5000),
        }
    }


def _generate_dashboard_config(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Generate dashboard configuration."""
    return {
        "name": settings.get("name", "default_dashboard"),
        "description": settings.get("description", "Default monitoring dashboard"),
        "refresh_interval_seconds": settings.get("refresh_interval_seconds", 30),
        "widgets": settings.get("widgets", []),
        "layout": settings.get("layout", {
            "columns": 3,
            "rows": "auto"
        }),
        "theme": settings.get("theme", "dark"),
        "timezone": settings.get("timezone", "UTC")
    }


def _generate_agent_config(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Generate agent configuration."""
    return {
        "name": settings.get("name", "DevRelAgent"),
        "version": settings.get("version", "1.0.0"),
        "llm_provider": {
            "type": settings.get("llm_type", "openai"),
            "model": settings.get("model", "gpt-4"),
            "api_key": settings.get("api_key", ""),
            "temperature": settings.get("temperature", 0.7),
            "max_tokens": settings.get("max_tokens", 2000),
        },
        "tools": {
            "enabled": settings.get("tools_enabled", True),
            "timeout_seconds": settings.get("tool_timeout", 30),
            "max_retries": settings.get("max_retries", 3),
        },
        "approvals": {
            "enabled": settings.get("approvals_enabled", True),
            "timeout_seconds": settings.get("approval_timeout", 300),
            "auto_approve_safe": settings.get("auto_approve_safe", False),
        },
        "logging": {
            "level": settings.get("log_level", "INFO"),
            "file": settings.get("log_file", "devrelagent.log"),
            "rotation": settings.get("log_rotation", "daily"),
        }
    }


def _dict_to_env(config: Dict[str, Any], prefix: str = "") -> List[str]:
    """Convert dictionary to ENV format."""
    env_lines = []

    for key, value in config.items():
        full_key = f"{prefix}_{key}".upper() if prefix else key.upper()

        if isinstance(value, dict):
            env_lines.extend(_dict_to_env(value, full_key))
        elif isinstance(value, bool):
            env_lines.append(f"{full_key}={'true' if value else 'false'}")
        elif isinstance(value, list):
            env_lines.append(f"{full_key}={json.dumps(value)}")
        elif isinstance(value, str):
            # Don't log sensitive values
            if any(sensitive in key.lower() for sensitive in ["password", "token", "secret", "key"]):
                env_lines.append(f"{full_key}=[REDACTED]")
            else:
                env_lines.append(f"{full_key}={value}")
        else:
            env_lines.append(f"{full_key}={value}")

    return env_lines


# ============== Tool Implementations ==============

@tool(
    name="generate_config",
    description="Generate system configuration files for various components",
    category=ToolCategory.SYSTEM,
    read_only=True
)
async def generate_config(
    config_type: Literal["clickhouse", "github", "dashboard", "agent"],
    settings: Dict[str, Any],
    output_format: Literal["json", "yaml", "env"] = "json"
) -> Dict[str, Any]:
    """
    Generate configuration file for specified system.

    Args:
        config_type: Type of configuration to generate
        settings: Configuration parameters (dictionary)
        output_format: Output format (json/yaml/env)

    Returns:
        Generated configuration content with metadata
    """
    config_templates = {
        "clickhouse": _generate_clickhouse_config,
        "github": _generate_github_config,
        "dashboard": _generate_dashboard_config,
        "agent": _generate_agent_config
    }

    generator = config_templates.get(config_type)
    if not generator:
        return {
            "success": False,
            "error": f"Unknown config type: {config_type}. Valid types: {list(config_templates.keys())}"
        }

    try:
        # Generate config
        config_content = generator(settings)

        # Format output
        if output_format == "yaml":
            try:
                import yaml
                formatted = yaml.dump(config_content, default_flow_style=False)
            except ImportError:
                formatted = "# PyYAML not installed, falling back to JSON\n" + json.dumps(config_content, indent=2)
        elif output_format == "env":
            env_lines = _dict_to_env(config_content)
            formatted = "\n".join(env_lines)
        else:
            formatted = json.dumps(config_content, indent=2)

        logger.info(f"Generated {config_type} config in {output_format} format")

        return {
            "success": True,
            "config_type": config_type,
            "format": output_format,
            "content": formatted,
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "settings_keys": list(settings.keys()),
                "preview_length": len(formatted)
            }
        }

    except Exception as e:
        logger.error(f"Config generation failed: {e}")
        return {
            "success": False,
            "error": f"Config generation failed: {str(e)}"
        }


@tool(
    name="validate_config",
    description="Validate configuration files against schema and requirements",
    category=ToolCategory.SYSTEM,
    read_only=True
)
async def validate_config(
    config_type: str,
    config_content: str,
    content_format: Literal["json", "yaml", "env"] = "json"
) -> Dict[str, Any]:
    """
    Validate configuration file for the specified type.

    Args:
        config_type: Type of configuration to validate
        config_content: Configuration content to validate
        content_format: Format of the content (json/yaml/env)

    Returns:
        Validation result with errors/warnings
    """
    try:
        # Parse content based on format
        if content_format == "json":
            config = json.loads(config_content)
        elif content_format == "yaml":
            try:
                import yaml
                config = yaml.safe_load(config_content)
            except ImportError:
                return {
                    "valid": False,
                    "error": "PyYAML not installed, cannot validate YAML format"
                }
        elif content_format == "env":
            # Parse ENV format (simple key=value)
            config = {}
            for line in config_content.strip().split("\n"):
                if "=" in line and not line.strip().startswith("#"):
                    key, value = line.split("=", 1)
                    config[key.strip()] = value.strip()
        else:
            return {
                "valid": False,
                "error": f"Unknown format: {content_format}"
            }

        # Validate based on config type
        validation_errors = []
        validation_warnings = []

        if config_type == "clickhouse":
            # Required fields
            required_fields = ["host", "port", "database"]
            for field in required_fields:
                if field not in config:
                    validation_errors.append(f"Missing required field: {field}")

            # Type checks
            if "port" in config and not isinstance(config["port"], int):
                validation_errors.append("Port must be an integer")

        elif config_type == "github":
            required_fields = ["api_base", "token"]
            for field in required_fields:
                if field not in config:
                    validation_errors.append(f"Missing required field: {field}")

        elif config_type == "dashboard":
            required_fields = ["name", "widgets"]
            for field in required_fields:
                if field not in config:
                    validation_errors.append(f"Missing required field: {field}")

            if "widgets" in config and not isinstance(config["widgets"], list):
                validation_errors.append("Widgets must be a list")

        elif config_type == "agent":
            required_fields = ["llm_provider", "tools"]
            for field in required_fields:
                if field not in config:
                    validation_errors.append(f"Missing required field: {field}")

        # Generate result
        is_valid = len(validation_errors) == 0

        return {
            "valid": is_valid,
            "config_type": config_type,
            "errors": validation_errors,
            "warnings": validation_warnings,
            "metadata": {
                "validated_at": datetime.now().isoformat(),
                "fields_checked": len(config),
                "format": content_format
            }
        }

    except json.JSONDecodeError as e:
        return {
            "valid": False,
            "error": f"Invalid JSON: {str(e)}"
        }
    except Exception as e:
        return {
            "valid": False,
            "error": f"Validation failed: {str(e)}"
        }


@tool(
    name="apply_config",
    description="Apply configuration to system (requires approval for write operations)",
    category=ToolCategory.SYSTEM,
    requires_approval=True,
    approval_action_type="write_operation",
    read_only=False,
    risk_level="critical"
)
async def apply_config(
    config_type: str,
    config_content: str,
    backup: bool = True,
    config_file_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Apply configuration to system with optional backup.

    ⚠️ WARNING: This will modify system configuration files.

    Args:
        config_type: Type of configuration to apply
        config_content: Configuration content to apply
        backup: Create backup before applying (recommended)
        config_file_path: Optional custom file path (default: auto-detected)

    Returns:
        Application result with backup location
    """
    try:
        # Determine file path
        if not config_file_path:
            config_paths = {
                "clickhouse": "config/clickhouse.json",
                "github": "config/github.json",
                "dashboard": "config/dashboard.json",
                "agent": "config/agent.json"
            }
            config_file_path = config_paths.get(config_type)
            if not config_file_path:
                return {
                    "success": False,
                    "error": f"Unknown config type: {config_type}"
                }

        # Create backup if requested
        backup_path = None
        if backup:
            try:
                import shutil
                from pathlib import Path

                file_path = Path(config_file_path)
                if file_path.exists():
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    backup_path = f"{config_file_path}.backup_{timestamp}"
                    shutil.copy2(config_file_path, backup_path)
                    logger.info(f"Created backup: {backup_path}")
            except Exception as e:
                logger.warning(f"Backup creation failed: {e}")
                backup_path = None

        # Create directory if it doesn't exist
        from pathlib import Path
        Path(config_file_path).parent.mkdir(parents=True, exist_ok=True)

        # Write configuration
        with open(config_file_path, 'w') as f:
            # Determine format from file extension or default to JSON
            if config_file_path.endswith('.yaml') or config_file_path.endswith('.yml'):
                # Assume YAML format
                try:
                    import yaml
                    # Parse and reformat to ensure validity
                    config = yaml.safe_load(config_content)
                    yaml.dump(config, f, default_flow_style=False)
                except ImportError:
                    f.write(config_content)
            else:
                # Default to JSON
                config = json.loads(config_content)
                json.dump(config, f, indent=2)

        logger.info(f"Applied {config_type} config to {config_file_path}")

        return {
            "success": True,
            "config_type": config_type,
            "file_path": config_file_path,
            "backup_path": backup_path,
            "metadata": {
                "applied_at": datetime.now().isoformat(),
                "backup_created": backup_path is not None
            }
        }

    except Exception as e:
        logger.error(f"Config application failed: {e}")
        return {
            "success": False,
            "error": f"Config application failed: {str(e)}"
        }


@tool(
    name="list_config_templates",
    description="List available configuration templates and their requirements",
    category=ToolCategory.SYSTEM,
    read_only=True
)
async def list_config_templates() -> Dict[str, Any]:
    """
    List all available configuration templates.

    Returns:
        Dictionary of available config types and their requirements
    """
    return {
        "success": True,
        "templates": {
            "clickhouse": {
                "description": "ClickHouse database connection configuration",
                "required_fields": ["host", "port", "database"],
                "optional_fields": ["user", "password", "secure", "connect_timeout", "send_receive_timeout", "compress", "settings"],
                "output_formats": ["json", "yaml", "env"]
            },
            "github": {
                "description": "GitHub API configuration",
                "required_fields": ["api_base", "token"],
                "optional_fields": ["default_branch", "repositories", "webhook_secret", "rate_limit"],
                "output_formats": ["json", "yaml", "env"]
            },
            "dashboard": {
                "description": "Dashboard configuration",
                "required_fields": ["name", "widgets"],
                "optional_fields": ["description", "refresh_interval_seconds", "layout", "theme", "timezone"],
                "output_formats": ["json", "yaml", "env"]
            },
            "agent": {
                "description": "Agent behavior configuration",
                "required_fields": ["llm_provider", "tools"],
                "optional_fields": ["approvals", "logging", "name", "version"],
                "output_formats": ["json", "yaml", "env"]
            }
        },
        "metadata": {
            "total_templates": 4,
            "supported_formats": ["json", "yaml", "env"]
        }
    }
