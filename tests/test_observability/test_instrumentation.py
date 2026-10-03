"""Phase 5: real instrumentation hooks (tool execution, audit labels)."""

from audit.logger import _metric_label
from guardrails.tool_guard import ToolGuardrail, _tool_outcome
from observability.metrics import get_metrics


async def test_tool_execution_records_outcome_metric(db_engine):
    guard = ToolGuardrail()

    async def handler(arguments):
        return {"ok": True}

    result = await guard.execute("observability_unit_tool", handler, {})
    assert result.success is True

    counter = get_metrics().counter(
        "devrel_tool_calls_total",
        "Total tool executions by outcome",
        ("tool", "outcome"),
    )
    assert counter.value({"tool": "observability_unit_tool", "outcome": "success"}) == 1


def test_tool_outcome_classifies_failures():
    class _Result:
        circuit_breaker_open = False
        rate_limited = False
        scope_violation = False
        timeout_occurred = False
        success = False

    assert _tool_outcome(_Result()) == "error"
    _Result.rate_limited = True
    assert _tool_outcome(_Result()) == "rate_limited"


def test_metric_label_renders_enum_and_string():
    from audit.schemas import ActionType

    assert _metric_label(ActionType.TOOL_CALL) == "tool_call"
    assert _metric_label("custom") == "custom"
    assert _metric_label(None) == "unknown"
