"""A small, dependency-free metrics registry with Prometheus exposition.

DevRelAgent needs counters, gauges and histograms on the request/agent path,
but the whole observability story should not depend on a heavyweight client
library. This module implements just enough of the Prometheus data model —
labelled counters, gauges and histograms — and renders the standard text
exposition format, so a scrape by Prometheus (or any compatible collector)
works out of the box.

All metrics are process-local aggregates. In a multi-replica deployment each
replica exposes its own ``/metrics``; aggregation is the scraper's job.
"""

from __future__ import annotations

import math
import threading
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

_DEFAULT_BUCKETS: Tuple[float, ...] = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)

LabelKey = Tuple[str, ...]


def _escape(value: str) -> str:
    """Escape a label value for the text exposition format."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _fmt_num(value: float) -> str:
    """Render a number the way Prometheus expects."""
    if isinstance(value, int):
        return str(value)
    if value != value or value in (math.inf, -math.inf):  # NaN / inf
        return str(value)
    if float(value).is_integer():
        return str(int(value))
    return repr(float(value))


def _render_labels(pairs: Sequence[Tuple[str, str]]) -> str:
    if not pairs:
        return ""
    body = ",".join(f'{name}="{_escape(value)}"' for name, value in pairs)
    return "{" + body + "}"


class _Metric:
    kind = "untyped"

    def __init__(self, name: str, help_text: str, label_names: Sequence[str] = ()) -> None:
        self.name = name
        self.help = help_text
        self.label_names = tuple(label_names)
        self._lock = threading.Lock()

    def _key(self, labels: Optional[Dict[str, str]]) -> LabelKey:
        if not self.label_names:
            return ()
        mapping = labels or {}
        return tuple(str(mapping.get(name, "")) for name in self.label_names)

    def _label_pairs(self, key: LabelKey) -> List[Tuple[str, str]]:
        return list(zip(self.label_names, key))

    def lines(self) -> Iterable[str]:  # pragma: no cover - overridden
        return ()


class Counter(_Metric):
    kind = "counter"

    def __init__(self, name: str, help_text: str, label_names: Sequence[str] = ()) -> None:
        super().__init__(name, help_text, label_names)
        self._values: Dict[LabelKey, float] = {}

    def inc(self, amount: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        key = self._key(labels)
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + amount

    def value(self, labels: Optional[Dict[str, str]] = None) -> float:
        return self._values.get(self._key(labels), 0.0)

    def lines(self) -> Iterable[str]:
        with self._lock:
            items = list(self._values.items())
        for key, value in items:
            yield f"{self.name}{_render_labels(self._label_pairs(key))} {_fmt_num(value)}"


class Gauge(_Metric):
    kind = "gauge"

    def __init__(self, name: str, help_text: str, label_names: Sequence[str] = ()) -> None:
        super().__init__(name, help_text, label_names)
        self._values: Dict[LabelKey, float] = {}

    def set(self, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        with self._lock:
            self._values[self._key(labels)] = float(value)

    def inc(self, amount: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        with self._lock:
            key = self._key(labels)
            self._values[key] = self._values.get(key, 0.0) + amount

    def dec(self, amount: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        self.inc(-amount, labels)

    def value(self, labels: Optional[Dict[str, str]] = None) -> float:
        return self._values.get(self._key(labels), 0.0)

    def lines(self) -> Iterable[str]:
        with self._lock:
            items = list(self._values.items())
        for key, value in items:
            yield f"{self.name}{_render_labels(self._label_pairs(key))} {_fmt_num(value)}"


class Histogram(_Metric):
    kind = "histogram"

    def __init__(
        self,
        name: str,
        help_text: str,
        label_names: Sequence[str] = (),
        buckets: Sequence[float] = _DEFAULT_BUCKETS,
    ) -> None:
        super().__init__(name, help_text, label_names)
        if list(buckets) != sorted(buckets):
            raise ValueError("histogram buckets must be sorted")
        self.buckets = tuple(float(b) for b in buckets)
        self._counts: Dict[LabelKey, List[int]] = {}
        self._sums: Dict[LabelKey, float] = {}
        self._totals: Dict[LabelKey, int] = {}

    def observe(self, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        key = self._key(labels)
        with self._lock:
            counts = self._counts.setdefault(key, [0] * len(self.buckets))
            for index, bound in enumerate(self.buckets):
                if value <= bound:
                    counts[index] += 1
                    break
            self._sums[key] = self._sums.get(key, 0.0) + float(value)
            self._totals[key] = self._totals.get(key, 0) + 1

    def count(self, labels: Optional[Dict[str, str]] = None) -> int:
        return self._totals.get(self._key(labels), 0)

    def total(self, labels: Optional[Dict[str, str]] = None) -> float:
        return self._sums.get(self._key(labels), 0.0)

    def lines(self) -> Iterable[str]:
        with self._lock:
            items = list(self._counts.items())
        for key, counts in items:
            base = self._label_pairs(key)
            cumulative = 0
            for bound, count in zip(self.buckets, counts):
                cumulative += count
                # Keep the bound verbatim ("1.0", not "1") so `le` labels are stable.
                pairs = base + [("le", str(float(bound)))]
                yield f"{self.name}_bucket{_render_labels(pairs)} {cumulative}"
            inf_pairs = base + [("le", "+Inf")]
            yield f"{self.name}_bucket{_render_labels(inf_pairs)} {self._totals[key]}"
            yield f"{self.name}_sum{_render_labels(base)} {_fmt_num(self._sums[key])}"
            yield f"{self.name}_count{_render_labels(base)} {self._totals[key]}"


class MetricsRegistry:
    """Creates and stores metrics, and renders the text exposition format."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._metrics: Dict[str, _Metric] = {}

    def _get(self, name: str, factory) -> _Metric:
        with self._lock:
            metric = self._metrics.get(name)
            if metric is None:
                metric = factory()
                self._metrics[name] = metric
            return metric

    def counter(self, name: str, help_text: str, label_names: Sequence[str] = ()) -> Counter:
        return self._get(  # type: ignore[return-value]
            name, lambda: Counter(name, help_text, label_names)
        )

    def gauge(self, name: str, help_text: str, label_names: Sequence[str] = ()) -> Gauge:
        return self._get(  # type: ignore[return-value]
            name, lambda: Gauge(name, help_text, label_names)
        )

    def histogram(
        self,
        name: str,
        help_text: str,
        label_names: Sequence[str] = (),
        buckets: Sequence[float] = _DEFAULT_BUCKETS,
    ) -> Histogram:
        return self._get(  # type: ignore[return-value]
            name, lambda: Histogram(name, help_text, label_names, buckets)
        )

    def reset(self) -> None:
        with self._lock:
            self._metrics.clear()

    def render(self) -> str:
        """Render every metric in the Prometheus text exposition format."""
        with self._lock:
            metrics = list(self._metrics.values())
        output: List[str] = []
        for metric in sorted(metrics, key=lambda m: m.name):
            output.append(f"# HELP {metric.name} {metric.help}")
            output.append(f"# TYPE {metric.name} {metric.kind}")
            output.extend(metric.lines())
        return "\n".join(output) + "\n"


_registry: Optional[MetricsRegistry] = None


def get_metrics() -> MetricsRegistry:
    """Return the process-wide metrics registry."""
    global _registry
    if _registry is None:
        _registry = MetricsRegistry()
    return _registry


def reset_metrics() -> None:
    """Drop all metrics (tests)."""
    global _registry
    _registry = None


__all__ = [
    "Counter",
    "Gauge",
    "Histogram",
    "MetricsRegistry",
    "get_metrics",
    "reset_metrics",
]
