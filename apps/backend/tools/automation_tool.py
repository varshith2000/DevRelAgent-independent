"""
Automation Tool — Action and Automation Layer

Provides tools for:
- OpenTelemetry configuration generation
- SDK setup snippets
- Environment variable generators
- Dashboard discovery and generation
- Structured ticket creation
- Severity assignment
"""

import logging
import os
from typing import Dict, Any, List, Optional, Literal
from datetime import datetime

from tools.registry import tool, ToolCategory

logger = logging.getLogger(__name__)


# ============== OpenTelemetry Configuration Generation ==============

@tool(
    name="generate_opentelemetry_config",
    description="Generate OpenTelemetry configuration for specified service and language",
    category=ToolCategory.SYSTEM,
    requires_approval=False,
    read_only=True,
    parameters={
        "service_name": {
            "type": "string",
            "description": "Name of the service"
        },
        "language": {
            "type": "string",
            "description": "Programming language/runtime",
            "enum": ["python", "javascript", "typescript", "java", "go", "dotnet", "ruby", "php"]
        },
        "otlp_endpoint": {
            "type": "string",
            "description": "OTLP endpoint (default: localhost:4317)",
            "default": "localhost:4317"
        },
        "enable_traces": {
            "type": "boolean",
            "description": "Enable tracing"
        },
        "enable_metrics": {
            "type": "boolean",
            "description": "Enable metrics"
        },
        "enable_logs": {
            "type": "boolean",
            "description": "Enable log correlation"
        }
    }
)
async def generate_opentelemetry_config(
    service_name: str,
    language: str,
    otlp_endpoint: str = "localhost:4317",
    enable_traces: bool = True,
    enable_metrics: bool = True,
    enable_logs: bool = False
) -> Dict[str, Any]:
    """
    Generate OpenTelemetry configuration for a service.

    Creates complete OTel configuration with SDK setup instructions.

    Args:
        service_name: Name of the service
        language: Programming language
        otlp_endpoint: OTLP endpoint
        enable_traces: Enable tracing
        enable_metrics: Enable metrics
        enable_logs: Enable log correlation

    Returns:
        Complete OTel configuration and setup instructions
    """
    try:
        configs = {
            "python": _generate_python_otel_config,
            "javascript": _generate_javascript_otel_config,
            "typescript": _generate_typescript_otel_config,
            "java": _generate_java_otel_config,
            "go": _generate_go_otel_config,
            "dotnet": _generate_dotnet_otel_config,
            "ruby": _generate_ruby_otel_config,
            "php": _generate_php_otel_config
        }

        generator = configs.get(language)
        if not generator:
            return {
                "success": False,
                "error": f"Language '{language}' not supported. Supported: {list(configs.keys())}"
            }

        config = generator(
            service_name=service_name,
            otlp_endpoint=otlp_endpoint,
            enable_traces=enable_traces,
            enable_metrics=enable_metrics,
            enable_logs=enable_logs
        )

        logger.info(f"Generated OTel config for {service_name} ({language})")

        return {
            "success": True,
            "service_name": service_name,
            "language": language,
            "config": config,
            "metadata": {
                "otlp_endpoint": otlp_endpoint,
                "features": {
                    "traces": enable_traces,
                    "metrics": enable_metrics,
                    "logs": enable_logs
                }
            }
        }

    except Exception as e:
        logger.error(f"generate_opentelemetry_config failed: {e}")
        return {
            "success": False,
            "error": f"Failed to generate OTel config: {str(e)}"
        }


def _generate_python_otel_config(**kwargs) -> Dict[str, Any]:
    """Generate Python OTel configuration."""
    return {
        "requirements": [
            "opentelemetry-api==1.22.0",
            "opentelemetry-sdk==1.22.0",
            "opentelemetry-instrumentation-flask==0.43b0",
            "opentelemetry-instrumentation-fastapi==0.43b0",
            "opentelemetry-instrumentation-httpx==0.43b0",
            "opentelemetry-exporter-otlp==1.22.0",
            "opentelemetry-semantic-conventions==0.43b0"
        ],
        "pip_install": "pip install " + " ".join([
            "opentelemetry-api",
            "opentelemetry-sdk",
            "opentelemetry-instrumentation-flask",
            "opentelemetry-instrumentation-fastapi",
            "opentelemetry-exporter-otlp"
        ]),
        "code_example": f'''
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource

# Configure resource
resource = Resource(attributes={{
    SERVICE_NAME: "{kwargs['service_name']}"
}})

# Configure tracer provider
trace.set_tracer_provider(TracerProvider(resource=resource))
tracer_provider = trace.get_tracer_provider()

# Add OTLP exporter
otlp_endpoint = "{kwargs['otlp_endpoint']}"
otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
span_processor = BatchSpanProcessor(otlp_exporter)
tracer_provider.add_span_processor(span_processor)

# Get tracer
tracer = trace.get_tracer(__name__)

# Use tracer
with tracer.start_as_current_span("operation-name") as span:
    span.set_attribute("key", "value")
    # Your code here
''',
        "environment_variables": {
            "OTEL_SERVICE_NAME": kwargs['service_name'],
            "OTEL_EXPORTER_OTLP_ENDPOINT": f"http://{kwargs['otlp_endpoint']}",
            "OTEL_EXPORTER_OTLP_INSECURE": "true",
            "OTEL_TRACES_EXPORTER": "otlp",
            "OTEL_METRICS_EXPORTER": "otlp" if kwargs['enable_metrics'] else "none",
            "OTEL_LOGS_EXPORTER": "otlp" if kwargs['enable_logs'] else "none"
        },
        "docker_compose_snippet": f'''
services:
  {kwargs['service_name']}:
    environment:
      - OTEL_SERVICE_NAME={kwargs['service_name']}
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://{kwargs['otlp_endpoint']}
      - OTEL_EXPORTER_OTLP_INSECURE=true
      - OTEL_TRACES_EXPORTER=otlp
      - OTEL_METRICS_EXPORTER=otlp
      - OTEL_LOGS_EXPORTER=otlp
'''
    }


def _generate_javascript_otel_config(**kwargs) -> Dict[str, Any]:
    """Generate JavaScript/Node.js OTel configuration."""
    return {
        "package_json": {
            "dependencies": {
                "@opentelemetry/api": "^1.7.0",
                "@opentelemetry/sdk-node": "^0.45.0",
                "@opentelemetry/auto-instrumentations": "^0.39.0"
            }
        },
        "npm_install": "npm install @opentelemetry/api @opentelemetry/sdk-node @opentelemetry/auto-instrumentations",
        "code_example": f'''
const {{ NodeTracerProvider }} = require('@opentelemetry/sdk-trace-node');
const {{ Resource }} = require('@opentelemetry/resources');
const {{ SemanticResourceAttributes }} = require('@opentelemetry/semantic-conventions');
const {{ OTLPTraceExporter }} = require('@opentelemetry/exporter-trace-otlp-grpc');

// Configure provider
const provider = new NodeTracerProvider({{
  resource: new Resource({{
    [SemanticResourceAttributes.SERVICE_NAME]: '{kwargs['service_name']}',
  }}),
}});

// Add OTLP exporter
const exporter = new OTLPTraceExporter({{
  url: 'http://{kwargs['otlp_endpoint']}',
}});
provider.addSpanProcessor(new BatchSpanProcessor(exporter));

// Register provider
provider.register();

// Your application code here
''',
        "environment_variables": {
            "OTEL_SERVICE_NAME": kwargs['service_name'],
            "OTEL_EXPORTER_OTLP_ENDPOINT": f"http://{kwargs['otlp_endpoint']}",
            "OTEL_NODE_RESOURCE_DETECTORS": "env,docker,container"
        }
    }


def _generate_typescript_otel_config(**kwargs) -> Dict[str, Any]:
    """Generate TypeScript OTel configuration."""
    config = _generate_javascript_otel_config(**kwargs)
    config["language"] = "typescript"
    config["ts_install"] = "npm install @opentelemetry/api @opentelemetry/sdk-node @opentelemetry/auto-instrumentations --save-dev"
    config["typescript_example"] = '''
import { NodeTracerProvider } from '@opentelemetry/sdk-trace-node';
import { Resource } from '@opentelemetry/resources';
import { SemanticResourceAttributes } from '@opentelemetry/semantic-conventions';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-grpc';

// TypeScript types are included
const provider: NodeTracerProvider = new NodeTracerProvider({
  resource: new Resource({
    [SemanticResourceAttributes.SERVICE_NAME]: 'my-service',
  }),
});
'''
    return config


def _generate_java_otel_config(**kwargs) -> Dict[str, Any]:
    """Generate Java OTel configuration."""
    return {
        "maven_dependencies": [
            "io.opentelemetry:opentelemetry-api:1.31.0",
            "io.opentelemetry:opentelemetry-sdk-trace:1.31.0",
            "io.opentelemetry:opentelemetry-exporter-otlp:1.31.0",
            "io.opentelemetry.instrumentation:opentelemetry-instrumentation-annotations:1.31.0"
        ],
        "gradle_dependencies": '''
implementation 'io.opentelemetry:opentelemetry-api:1.31.0'
implementation 'io.opentelemetry:opentelemetry-sdk-trace:1.31.0'
implementation 'io.opentelemetry:opentelemetry-exporter-otlp:1.31.0'
implementation 'io.opentelemetry.instrumentation:opentelemetry-instrumentation-annotations:1.31.0'
''',
        "code_example": f'''
import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Context;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import io.opentelemetry.sdk.trace.export.BatchSpanProcessor;
import io.opentelemetry.exporter.otlp.trace.OtlpGrpcSpanExporter;
import io.opentelemetry.sdk.resources.Resource;

// Configure resource
Resource resource = Resource.getDefault()
    .toBuilder()
    .put("service.name", "{kwargs['service_name']}")
    .build();

// Configure tracer provider
SdkTracerProvider tracerProvider = SdkTracerProvider.builder()
    .setResource(resource)
    .addSpanProcessor(BatchSpanProcessor.builder()
        .setExporter(OtlpGrpcSpanExporter.builder()
            .setEndpoint("http://{kwargs['otlp_endpoint']}")
            .build())
        .build())
    .build();

// Register globally
OpenTelemetry.setOpenTelemetry(
    OpenTelemetrySdk.builder()
        .setTracerProvider(tracerProvider)
        .buildAndRegisterGlobal()
);

// Get tracer
Tracer tracer = tracerProvider.get("{kwargs['service_name']}", "1.0.0");

// Use tracer
try (Scope scope = tracer.spanBuilder("operation-name").startSpan()) {{
    Span span = tracer.getCurrentSpan();
    span.setAttribute("key", "value");
    // Your code here
}}
''',
        "environment_variables": {
            "OTEL_SERVICE_NAME": kwargs['service_name'],
            "OTEL_EXPORTER_OTLP_ENDPOINT": f"http://{kwargs['otlp_endpoint']}",
            "OTEL_TRACES_EXPORTER": "otlp",
            "OTEL_METRICS_EXPORTER": "otlp" if kwargs['enable_metrics'] else "none"
        },
        "javaagent": f'''
# Download and use Java agent (alternative to manual setup)
java -javaagent:opentelemetry-javaagent.jar \\
     -Dotel.service.name={kwargs['service_name']} \\
     -Dotel.exporter.otlp.endpoint=http://{kwargs['otlp_endpoint']} \\
     -jar your-application.jar
'''
    }


def _generate_go_otel_config(**kwargs) -> Dict[str, Any]:
    """Generate Go OTel configuration."""
    return {
        "go_mod": '''
require (
    go.opentelemetry.io/otel v1.21.0
    go.opentelemetry.io/otel/trace v1.21.0
    go.opentelemetry.io/otel/sdk v1.21.0
    go.opentelemetry.io/otel/exporters/otlp/otlptrace v1.21.0
    go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc v1.21.0
    go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp v0.46.1
)
''',
        "go_get": "go get go.opentelemetry.io/otel@latest go.opentelemetry.io/otel/trace@latest",
        "code_example": f'''
package main

import (
    "context"
    "log"

    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/attribute"
    "go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
    "go.opentelemetry.io/otel/sdk/resource"
    tracesdk "go.opentelemetry.io/otel/sdk/trace"
    "go.opentelemetry.io/otel/trace"
)

func initTracer() {{
    // Configure resource
    res, _ := resource.New(
        context.Background(),
        resource.WithAttributes(
            attribute.String("service.name", "{kwargs['service_name']}"),
        ),
    )

    // Configure OTLP exporter
    exporter, _ := otlptracegrpc.New(
        context.Background(),
        otlptracegrpc.WithEndpoint("{kwargs['otlp_endpoint']}"),
        otlptracegrpc.WithInsecure(),
    )

    // Configure tracer provider
    tp := tracesdk.NewTracerProvider(
        tracesdk.WithResource(res),
        tracesdk.WithBatcher(exporter),
    )

    // Register globally
    otel.SetTracerProvider(tp)
}}

func main() {{
    initTracer()

    tracer := otel.Tracer("{kwargs['service_name']}")
    ctx, span := tracer.Start(context.Background(), "operation-name")
    defer span.End()

    span.SetAttributes("key", "value")

    // Your code here
}}
''',
        "environment_variables": {
            "OTEL_SERVICE_NAME": kwargs['service_name'],
            "OTEL_EXPORTER_OTLP_ENDPOINT": f"http://{kwargs['otlp_endpoint']}",
            "OTEL_TRACES_EXPORTER": "otlp"
        }
    }


def _generate_dotnet_otel_config(**kwargs) -> Dict[str, Any]:
    """Generate .NET OTel configuration."""
    return {
        "nuget_packages": [
            "OpenTelemetry",
            "OpenTelemetry.Exporter.OpenTelemetryProtocol",
            "OpenTelemetry.Extensions.Hosting",
            "OpenTelemetry.Instrumentation.AspNetCore",
            "OpenTelemetry.Instrumentation.Http"
        ],
        "dotnet_add": '''
dotnet add package OpenTelemetry
dotnet add package OpenTelemetry.Exporter.OpenTelemetryProtocol
dotnet add package OpenTelemetry.Extensions.Hosting
dotnet add package OpenTelemetry.Instrumentation.AspNetCore
''',
        "program_cs": f'''
using OpenTelemetry;
using OpenTelemetry.Trace;
using OpenTelemetry.Resources;
using OpenTelemetry.Exporter.OpenTelemetryProtocol;

var builder = WebApplication.CreateBuilder(args);

// Add OpenTelemetry
builder.Services.AddOpenTelemetry()
    .ConfigureResource(resource => resource
        .AddService("{kwargs['service_name']}"))
    .WithTracing(tracing => tracing
        .AddAspNetCoreInstrumentation()
        .AddHttpClientInstrumentation()
        .AddOtlpExporter(otlpOptions =>
        {{
            otlpOptions.Endpoint = new Uri("http://{kwargs['otlp_endpoint']}");
        }}));

var app = builder.Build();

app.Run();
''',
        "environment_variables": {
            "OTEL_SERVICE_NAME": kwargs['service_name'],
            "OTEL_EXPORTER_OTLP_ENDPOINT": f"http://{kwargs['otlp_endpoint']}"
        }
    }


def _generate_ruby_otel_config(**kwargs) -> Dict[str, Any]:
    """Generate Ruby OTel configuration."""
    return {
        "gemfile": '''
gem 'opentelemetry-api'
gem 'opentelemetry-sdk'
gem 'opentelemetry-exporter-otlp'
gem 'opentelemetry-instrumentation-all'
''',
        "bundle_install": "bundle install",
        "code_example": f'''
require 'opentelemetry/sdk'
require 'opentelemetry/exporter/otlp'
require 'opentelemetry/instrumentation/all'

OpenTelemetry::SDK.configure do |c|
  c.service_name = '{kwargs['service_name']}'
  c.service_version = '1.0.0'

  c.add_span_processor(
    OpenTelemetry::Exporter::OTLP::SpanProcessor.new(
      endpoint: 'http://{kwargs['otlp_endpoint']}'
    )
  )
end

# Your application code
''',
        "environment_variables": {
            "OTEL_SERVICE_NAME": kwargs['service_name'],
            "OTEL_EXPORTER_OTLP_ENDPOINT": f"http://{kwargs['otlp_endpoint']}"
        }
    }


def _generate_php_otel_config(**kwargs) -> Dict[str, Any]:
    """Generate PHP OTel configuration."""
    return {
        "composer": '''
{
    "require": {
        "open-telemetry/api": "^1.0",
        "open-telemetry/sdk": "^1.0",
        "open-telemetry/exporter-otlp": "^1.0"
    }
}
''',
        "composer_install": "composer install",
        "code_example": f'''<?php
require __DIR__ . '/vendor/autoload.php';

use OpenTelemetry\\SDK\\Trace\\TracerProviderFactory;
use OpenTelemetry\\SDK\\Resource\\ResourceInfo;
use OpenTelemetry\\Exporter\\OTLP\\SpanExporter;

// Configure resource
$resource = ResourceInfo::create(
    attributes: [
        'service.name' => '{kwargs['service_name']}',
    ]
);

// Configure exporter
$exporter = new SpanExporter(
    endpoint: 'http://{kwargs['otlp_endpoint']}'
);

// Configure tracer provider
$tracerProvider = (new TracerProviderFactory())
    ->withResource($resource)
    ->addSpanProcessor(new BatchSpanProcessor($exporter))
    ->create();

// Get tracer
$tracer = $tracerProvider->getTracer('{kwargs['service_name']}');

// Use tracer
$span = $tracer->spanBuilder('operation-name')->startSpan();
$span->setAttribute('key', 'value');
// Your code here
$span->end();
?>
''',
        "environment_variables": {
            "OTEL_SERVICE_NAME": kwargs['service_name'],
            "OTEL_EXPORTER_OTLP_ENDPOINT": f"http://{kwargs['otlp_endpoint']}"
        }
    }


# ============== Environment Variable Generator ==============

@tool(
    name="generate_env_vars",
    description="Generate environment variables for observability stack",
    category=ToolCategory.SYSTEM,
    read_only=True,
    parameters={
        "service_name": {
            "type": "string",
            "description": "Service name"
        },
        "environment": {
            "type": "string",
            "description": "Environment (dev, staging, prod)",
            "enum": ["dev", "staging", "prod"]
        },
        "include_database": {
            "type": "boolean",
            "description": "Include database variables"
        },
        "include_cache": {
            "type": "boolean",
            "description": "Include cache variables"
        }
    }
)
async def generate_env_vars(
    service_name: str,
    environment: str = "dev",
    include_database: bool = True,
    include_cache: bool = True
) -> Dict[str, Any]:
    """
    Generate environment variables for service configuration.

    Args:
        service_name: Service name
        environment: Environment type
        include_database: Include database configuration
        include_cache: Include cache configuration

    Returns:
        Environment variables configuration
    """
    try:
        env_vars = {
            # Service configuration
            "SERVICE_NAME": service_name,
            "ENVIRONMENT": environment,
            "LOG_LEVEL": "INFO" if environment != "prod" else "WARN",

            # Observability
            "OTEL_SERVICE_NAME": service_name,
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317",
            "OTEL_EXPORTER_OTLP_INSECURE": "true",
            "OTEL_TRACES_EXPORTER": "otlp",
            "OTEL_METRICS_EXPORTER": "otlp",
        }

        # Add database variables if requested
        if include_database:
            env_vars.update({
                "DATABASE_HOST": os.getenv("DATABASE_HOST", "localhost"),
                "DATABASE_PORT": os.getenv("DATABASE_PORT", "5432"),
                "DATABASE_NAME": os.getenv("DATABASE_NAME", f"{service_name}_{environment}"),
                "DATABASE_USER": os.getenv("DATABASE_USER", "user"),
                "DATABASE_SSL_MODE": os.getenv("DATABASE_SSL_MODE", "require" if environment == "prod" else "disable"),
                "DATABASE_POOL_SIZE": "10" if environment == "dev" else "50",
                "DATABASE_TIMEOUT_SECONDS": "30",
            })

        # Add cache variables if requested
        if include_cache:
            env_vars.update({
                "CACHE_HOST": os.getenv("CACHE_HOST", "localhost"),
                "CACHE_PORT": os.getenv("CACHE_PORT", "6379"),
                "CACHE_DB": os.getenv("CACHE_DB", "0"),
                "CACHE_TTL_SECONDS": "3600",
                "CACHE_MAX_CONNECTIONS": "10",
            })

        # Format as different file types
        return {
            "success": True,
            "formats": {
                "bash": "\n".join(f'export {k}="{v}"' for k, v in env_vars.items()),
                "dotenv": "\n".join(f'{k}={v}' for k, v in env_vars.items()),
                "docker_env": "\n".join(f'{k}={v}' for k, v in env_vars.items()),
                "json": env_vars
            },
            "metadata": {
                "service_name": service_name,
                "environment": environment,
                "total_vars": len(env_vars)
            }
        }

    except Exception as e:
        logger.error(f"generate_env_vars failed: {e}")
        return {
            "success": False,
            "error": f"Failed to generate env vars: {str(e)}"
        }


# ============== Dashboard Discovery ==============

@tool(
    name="discover_dashboards",
    description="Discover existing dashboards for a service or pattern",
    category=ToolCategory.SYSTEM,
    read_only=True,
    parameters={
        "service": {
            "type": "string",
            "description": "Service name to search for"
        },
        "pattern": {
            "type": "string",
            "description": "Search pattern (alternative to service)"
        },
        "sources": {
            "type": "array",
            "description": "Dashboard sources to search",
            "items": {"type": "string", "enum": ["grafana", "datadog", "prometheus", "custom"]}
        }
    }
)
async def discover_dashboards(
    service: Optional[str] = None,
    pattern: Optional[str] = None,
    sources: List[str] = ["grafana", "custom"]
) -> Dict[str, Any]:
    """
    Discover existing dashboards for a service.

    Args:
        service: Service name
        pattern: Search pattern
        sources: Dashboard sources to search

    Returns:
        Discovered dashboards
    """
    try:
        # This is a placeholder implementation
        # In production, would query actual dashboard systems

        discovered = []

        # Check custom dashboards
        if "custom" in sources:
            from tools.dashboard_tool import list_dashboards
            result = await list_dashboards()

            if result.get("success"):
                for dash in result.get("dashboards", []):
                    dash_name = dash.get("name", "").lower()

                    # Filter by service or pattern
                    if service and service.lower() in dash_name:
                        discovered.append({
                            "source": "custom",
                            "id": dash.get("id"),
                            "name": dash.get("name"),
                            "description": dash.get("description"),
                            "widget_count": dash.get("widget_count"),
                            "url": f"/dashboard/{dash.get('id')}"
                        })
                    elif pattern and pattern.lower() in dash_name:
                        discovered.append({
                            "source": "custom",
                            "id": dash.get("id"),
                            "name": dash.get("name"),
                            "description": dash.get("description"),
                            "widget_count": dash.get("widget_count"),
                            "url": f"/dashboard/{dash.get('id')}"
                        })

        # Check Grafana (placeholder)
        if "grafana" in sources:
            # In production, query Grafana API
            discovered.append({
                "source": "grafana",
                "id": f"grafana-{service or pattern}",
                "name": f"{service or 'Service'} Overview",
                "description": "Grafana dashboard (if configured)",
                "url": "/grafana/d/overview",
                "note": "Configure Grafana integration for actual dashboards"
            })

        return {
            "success": True,
            "dashboards": discovered,
            "total": len(discovered),
            "metadata": {
                "service": service,
                "pattern": pattern,
                "sources_searched": sources
            }
        }

    except Exception as e:
        logger.error(f"discover_dashboards failed: {e}")
        return {
            "success": False,
            "error": f"Failed to discover dashboards: {str(e)}"
        }


# ============== Severity Assignment ==============

@tool(
    name="assign_severity",
    description="Assign severity level to an issue or alert based on impact and urgency",
    category=ToolCategory.UTILITY,
    read_only=True,
    parameters={
        "impact": {
            "type": "string",
            "description": "Impact level",
            "enum": ["critical", "high", "medium", "low"]
        },
        "urgency": {
            "type": "string",
            "description": "Urgency level",
            "enum": ["immediate", "urgent", "normal", "low"]
        },
        "affected_users": {
            "type": "integer",
            "description": "Number of affected users (optional)"
        },
        "business_impact": {
            "type": "string",
            "description": "Business impact description"
        }
    }
)
async def assign_severity(
    impact: str,
    urgency: str,
    affected_users: Optional[int] = None,
    business_impact: Optional[str] = None
) -> Dict[str, Any]:
    """
    Assign severity level based on impact and urgency.

    Uses a severity matrix to determine the appropriate level.

    Args:
        impact: Impact level
        urgency: Urgency level
        affected_users: Number of affected users
        business_impact: Business impact description

    Returns:
        Assigned severity with reasoning
    """
    try:
        # Severity matrix
        # Rows: Impact (critical, high, medium, low)
        # Columns: Urgency (immediate, urgent, normal, low)

        severity_matrix = {
            ("critical", "immediate"): "P0",
            ("critical", "urgent"): "P0",
            ("critical", "normal"): "P1",
            ("critical", "low"): "P2",

            ("high", "immediate"): "P0",
            ("high", "urgent"): "P1",
            ("high", "normal"): "P1",
            ("high", "low"): "P2",

            ("medium", "immediate"): "P1",
            ("medium", "urgent"): "P2",
            ("medium", "normal"): "P2",
            ("medium", "low"): "P3",

            ("low", "immediate"): "P2",
            ("low", "urgent"): "P3",
            ("low", "normal"): "P3",
            ("low", "low"): "P4",
        }

        # Get severity from matrix
        severity = severity_matrix.get((impact, urgency), "P3")

        # Adjust based on affected users
        if affected_users is not None:
            if affected_users > 10000 and severity != "P0":
                severity = "P0"
            elif affected_users > 5000 and severity in ["P2", "P3", "P4"]:
                severity = "P1"
            elif affected_users > 1000 and severity in ["P3", "P4"]:
                severity = "P2"

        # Severity descriptions
        severity_descriptions = {
            "P0": "Critical - System down, data loss, or security breach. Immediate action required.",
            "P1": "High - Major feature broken or significant degradation. Urgent action required.",
            "P2": "Medium - Minor feature degraded or workaround available. Normal priority.",
            "P3": "Low - Cosmetic issue or minor inconvenience. Low priority.",
            "P4": "Informational - Enhancement or improvement opportunity. Very low priority."
        }

        # Suggested labels
        labels_map = {
            "P0": ["critical", "severity:P0", "priority:critical"],
            "P1": ["high", "severity:P1", "priority:high"],
            "P2": ["medium", "severity:P2", "priority:medium"],
            "P3": ["low", "severity:P3", "priority:low"],
            "P4": ["enhancement", "severity:P4", "priority:backlog"]
        }

        return {
            "success": True,
            "severity": severity,
            "description": severity_descriptions.get(severity),
            "labels": labels_map.get(severity, []),
            "suggested_sla": {
                "P0": "15 minutes",
                "P1": "1 hour",
                "P2": "4 hours",
                "P3": "1 day",
                "P4": "1 week"
            }.get(severity),
            "reasoning": f"""
Based on severity matrix:
- Impact: {impact}
- Urgency: {urgency}
- Affected users: {affected_users or 'N/A'}
- Business impact: {business_impact or 'N/A'}

Assigned severity: {severity}
""",
            "metadata": {
                "matrix_used": "impact_urgency_matrix",
                "adjusted_for_users": affected_users is not None
            }
        }

    except Exception as e:
        logger.error(f"assign_severity failed: {e}")
        return {
            "success": False,
            "error": f"Failed to assign severity: {str(e)}"
        }


# ============== Structured Ticket Creation ==============

@tool(
    name="create_structured_ticket",
    description="Create structured GitHub issue with proper formatting and labels",
    category=ToolCategory.API,
    requires_approval=True,
    approval_action_type="github_issue",
    read_only=False,
    risk_level="medium",
    parameters={
        "ticket_type": {
            "type": "string",
            "description": "Type of ticket",
            "enum": ["bug", "feature", "improvement", "documentation", "incident", "task"]
        },
        "title": {
            "type": "string",
            "description": "Ticket title"
        },
        "description": {
            "type": "string",
            "description": "Detailed description"
        },
        "severity": {
            "type": "string",
            "description": "Severity level",
            "enum": ["P0", "P1", "P2", "P3", "P4"]
        },
        "repo": {
            "type": "string",
            "description": "Repository (format: owner/repo)"
        },
        "service": {
            "type": "string",
            "description": "Affected service"
        },
        "environment": {
            "type": "string",
            "description": "Environment where issue occurs",
            "enum": ["dev", "staging", "prod", "all"]
        },
        "steps_to_reproduce": {
            "type": "array",
            "description": "Steps to reproduce (for bugs)",
            "items": {"type": "string"}
        },
        "expected_behavior": {
            "type": "string",
            "description": "Expected behavior (for bugs)"
        },
        "actual_behavior": {
            "type": "string",
            "description": "Actual behavior (for bugs)"
        },
        "acceptance_criteria": {
            "type": "array",
            "description": "Acceptance criteria (for features)",
            "items": {"type": "string"}
        }
    }
)
async def create_structured_ticket(
    ticket_type: str,
    title: str,
    description: str,
    severity: str,
    repo: str,
    service: Optional[str] = None,
    environment: Optional[str] = None,
    steps_to_reproduce: Optional[List[str]] = None,
    expected_behavior: Optional[str] = None,
    actual_behavior: Optional[str] = None,
    acceptance_criteria: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Create structured GitHub issue with proper formatting.

    Args:
        ticket_type: Type of ticket
        title: Ticket title
        description: Detailed description
        severity: Severity level (P0-P4)
        repo: Repository (owner/repo)
        service: Affected service
        environment: Environment
        steps_to_reproduce: Steps for bugs
        expected_behavior: Expected behavior
        actual_behavior: Actual behavior
        acceptance_criteria: Acceptance criteria for features

    Returns:
        Created issue information
    """
    try:
        # Build labels based on ticket type and severity
        type_labels = {
            "bug": ["bug", "type:bug"],
            "feature": ["enhancement", "type:feature"],
            "improvement": ["enhancement", "type:improvement"],
            "documentation": ["documentation", "type:docs"],
            "incident": ["incident", "type:incident"],
            "task": ["task"]
        }

        severity_labels = {
            "P0": ["critical", "severity:P0", "priority:critical"],
            "P1": ["high", "severity:P1", "priority:high"],
            "P2": ["medium", "severity:P2", "priority:medium"],
            "P3": ["low", "severity:P3", "priority:low"],
            "P4": ["backlog", "severity:P4", "priority:backlog"]
        }

        labels = type_labels.get(ticket_type, [])
        labels.extend(severity_labels.get(severity, []))

        # Add service label if provided
        if service:
            labels.append(f"service:{service}")

        # Add environment label if provided
        if environment:
            labels.append(f"env:{environment}")

        # Build issue body
        body_parts = [
            f"## {ticket_type.capitalize()}",
            "",
            description,
            ""
        ]

        # Add severity info
        body_parts.extend([
            f"## Severity",
            "",
            f"**Severity:** {severity}",
            ""
        ])

        # Add environment/service info
        if service or environment:
            body_parts.append("## Context")
            body_parts.append("")
            if service:
                body_parts.append(f"**Service:** {service}")
            if environment:
                body_parts.append(f"**Environment:** {environment}")
            body_parts.append("")

        # Add bug-specific sections
        if ticket_type == "bug":
            body_parts.extend([
                "## Steps to Reproduce",
                ""
            ])

            if steps_to_reproduce:
                for i, step in enumerate(steps_to_reproduce, 1):
                    body_parts.append(f"{i}. {step}")
            else:
                body_parts.append("No steps provided")

            body_parts.extend([
                "",
                "## Expected Behavior",
                "",
                expected_behavior or "Not provided",
                "",
                "## Actual Behavior",
                "",
                actual_behavior or "Not provided",
                ""
            ])

        # Add feature-specific sections
        if ticket_type == "feature" and acceptance_criteria:
            body_parts.extend([
                "## Acceptance Criteria",
                ""
            ])

            for i, criterion in enumerate(acceptance_criteria, 1):
                body_parts.append(f"- [ ] {criterion}")

            body_parts.append("")
        # Add metadata
        body_parts.extend([
            "---",
            "",
            "## Metadata",
            f"- **Created:** {datetime.now().isoformat()}",
            f"- **Type:** {ticket_type}",
            f"- **Severity:** {severity}",
            f"- **Service:** {service or 'N/A'}",
            "",
            "*This issue was created using the structured ticket creation tool.*"
        ])

        body = "\n".join(body_parts)

        # Create issue
        from tools.github_tool import draft_github_issue

        result = await draft_github_issue(
            repo=repo,
            title=f"[{severity}] {title}",
            body=body,
            labels=labels
        )

        if result.get("success"):
            return {
                "success": True,
                "ticket_url": result.get("issue_url"),
                "ticket_number": result.get("issue_number"),
                "metadata": {
                    "ticket_type": ticket_type,
                    "severity": severity,
                    "labels": labels,
                    "repo": repo
                }
            }
        else:
            return result

    except Exception as e:
        logger.error(f"create_structured_ticket failed: {e}")
        return {
            "success": False,
            "error": f"Failed to create ticket: {str(e)}"
        }
