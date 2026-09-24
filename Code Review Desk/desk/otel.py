from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    ConsoleSpanExporter,
    SimpleSpanProcessor,
    SpanExportResult,
)
from opentelemetry.trace import Span, Status, StatusCode, Tracer

from agents.tracing import TracingProcessor, add_trace_processor

_configured = False
_tracer: Tracer | None = None
DEFAULT_TRACE_PATH = Path("otel_trace.jsonl")


class JsonlSpanExporter:
    """Append finished spans to a local JSONL file so the trace can be opened."""

    def __init__(self, path: Path | str = DEFAULT_TRACE_PATH) -> None:
        self.path = Path(path)

    def export(self, spans) -> SpanExportResult:
        try:
            with self.path.open("a", encoding="utf-8") as f:
                for span in spans:
                    f.write(json.dumps(_span_to_dict(span), ensure_ascii=False) + "\n")
            return SpanExportResult.SUCCESS
        except Exception:
            return SpanExportResult.FAILURE

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True

    def shutdown(self) -> None:
        pass


def _span_to_dict(span: Any) -> dict[str, Any]:
    ctx = span.get_span_context()
    parent = getattr(span, "parent", None)
    parent_id = None
    if parent is not None:
        parent_id = format(parent.span_id, "016x")
    return {
        "name": span.name,
        "trace_id": format(ctx.trace_id, "032x"),
        "span_id": format(ctx.span_id, "016x"),
        "parent_span_id": parent_id,
        "start_ns": span.start_time,
        "end_ns": span.end_time,
        "attributes": {k: v for k, v in (span.attributes or {}).items()},
    }


def configure_opentelemetry(
    service_name: str = "code-review-desk",
    console: bool = False,
    trace_path: Path | str = DEFAULT_TRACE_PATH,
) -> Tracer:
    """Configure OpenTelemetry once; export under the ambient OPENAI_API_KEY setup."""
    global _configured, _tracer

    if _configured and _tracer is not None:
        return _tracer

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY must be set for OpenTelemetry tracing setup")

    resource = Resource.create({"service.name": service_name})
    try:
        trace.set_tracer_provider(TracerProvider(resource=resource))
    except Exception:
        pass

    provider = trace.get_tracer_provider()
    if isinstance(provider, TracerProvider):
        provider.add_span_processor(SimpleSpanProcessor(JsonlSpanExporter(trace_path)))
        if console:
            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

    _tracer = trace.get_tracer(service_name)
    _configured = True

    add_trace_processor(AgentsToOtelProcessor(_tracer))
    return _tracer


class _NullSpan:
    """No-op span used when OpenTelemetry is not configured."""

    def get_span_context(self):
        return None

    def set_attribute(self, *args, **kwargs) -> None:
        pass

    def set_status(self, *args, **kwargs) -> None:
        pass

    def end(self, *args, **kwargs) -> None:
        pass


def get_tracer() -> Tracer:
    global _tracer
    if _tracer is None:
        return configure_opentelemetry()
    return _tracer


def is_configured() -> bool:
    return _configured


class AgentsToOtelProcessor(TracingProcessor):
    """Bridge Agents SDK traces/spans into the active OpenTelemetry tracer.

    All spans emitted while a review is in flight nest under the current OTel
    context (the single review root span created by ``review_trace``).
    """

    def __init__(self, tracer: Tracer | None = None) -> None:
        self._tracer = tracer
        self._span_map: dict[str, Any] = {}
        self._trace_map: dict[str, str] = {}

    def _otel_tracer(self) -> Tracer:
        return self._tracer or get_tracer()

    def on_trace_start(self, trace) -> None:  # noqa: A002 - SDK signature
        try:
            self._trace_map[trace.trace_id] = trace.name
        except Exception:
            pass

    def on_trace_end(self, trace) -> None:  # noqa: A002
        self._trace_map.pop(getattr(trace, "trace_id", ""), None)

    def on_span_start(self, span) -> None:
        try:
            name = getattr(span.span_data, "type", None) or "agents.span"
            extra = _span_attributes(span.span_data)
            otel_span = self._otel_tracer().start_span(name, attributes=extra)
            self._span_map[span.span_id] = otel_span
        except Exception:
            self._span_map[span.span_id] = None

    def on_span_end(self, span) -> None:
        otel_span = self._span_map.pop(span.span_id, None)
        if otel_span is None:
            return
        try:
            err = getattr(span, "error", None)
            if err:
                otel_span.set_status(Status(StatusCode.ERROR, str(err)))
            otel_span.end()
        except Exception:
            try:
                otel_span.end()
            except Exception:
                pass

    def shutdown(self) -> None:
        for s in self._span_map.values():
            if s is not None:
                try:
                    s.end()
                except Exception:
                    pass
        self._span_map.clear()
        self._trace_map.clear()

    def force_flush(self) -> None:
        pass


def _span_attributes(span_data: Any) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    for key in ("name", "model", "type", "from_agent", "to_agent"):
        val = getattr(span_data, key, None)
        if isinstance(val, str):
            attrs[f"agents.{key}"] = val
    usage = getattr(span_data, "usage", None)
    if usage is not None:
        for uk in ("input_tokens", "output_tokens", "total_tokens", "requests"):
            uv = getattr(usage, uk, None)
            if isinstance(uv, int):
                attrs[f"agents.usage.{uk}"] = uv
    return attrs


@contextmanager
def review_trace(diff_path: str = "") -> Iterator[Span]:
    """Single OTel root span covering the entire review (all reviewers, merge, handoffs)."""
    if not _configured or _tracer is None:
        yield _NullSpan()
        return
    tracer = _tracer
    with tracer.start_as_current_span("code-review-desk.review") as span:
        if diff_path:
            span.set_attribute("review.diff_path", diff_path)
        span.set_attribute("review.reviewers", "SecurityReviewer,TestReviewer,StyleReviewer")
        yield span


@contextmanager
def reviewer_span(agent_name: str, **attrs: Any) -> Iterator[Span]:
    if not _configured or _tracer is None:
        yield _NullSpan()
        return
    tracer = _tracer
    with tracer.start_as_current_span(agent_name) as span:
        span.set_attribute("review.agent", agent_name)
        for k, v in attrs.items():
            span.set_attribute(k, v)
        yield span


def reset_for_tests() -> None:
    global _configured, _tracer
    _configured = False
    _tracer = None
