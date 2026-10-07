from agent.loop import AgentLoop
from models.schemas import SessionContext
from tools.registry import ToolRegistry


def test_explicit_otel_request_routes_to_registered_generator():
    registry = ToolRegistry()
    registry.register_manual(
        name="generate_opentelemetry_config",
        handler=lambda **kwargs: kwargs,
        description="Generate OpenTelemetry configuration",
    )
    agent = AgentLoop(tool_registry=registry)

    query = "Generate an OpenTelemetry configuration for a Python FastAPI service."
    perception = agent._perceive(query)

    assert perception.intent == "config_generation"
    assert perception.tool_hint == "generate_opentelemetry_config"
    assert agent._route_to_tool(perception, None) == "generate_opentelemetry_config"


def test_otel_request_arguments_include_service_and_language():
    registry = ToolRegistry()
    registry.register_manual(
        name="generate_opentelemetry_config",
        handler=lambda **kwargs: kwargs,
        description="Generate OpenTelemetry configuration",
    )
    agent = AgentLoop(tool_registry=registry)
    query = "Generate OpenTelemetry config for payments-api in Python."
    perception = agent._perceive(query)

    arguments = agent._build_tool_arguments(
        "generate_opentelemetry_config",
        perception,
        SessionContext(session_id="test-session"),
    )

    assert arguments == {
        "service_name": "payments-api",
        "language": "python",
        "otlp_endpoint": "localhost:4317",
        "enable_traces": True,
        "enable_metrics": True,
        "enable_logs": False,
    }
