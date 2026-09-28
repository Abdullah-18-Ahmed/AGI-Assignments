from __future__ import annotations

import os
import uuid
from contextvars import ContextVar
from typing import Optional

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import Span, SpanContext, TraceFlags, Tracer

from shop_desk.config.settings import get_settings


_trace_provider: Optional[TracerProvider] = None
_tracer: Optional[Tracer] = None
_current_session_id: ContextVar[Optional[str]] = ContextVar("current_session_id", default=None)
_current_trace_id: ContextVar[Optional[int]] = ContextVar("current_trace_id", default=None)
_current_span: ContextVar[Optional[Span]] = ContextVar("current_span", default=None)


def init_tracing() -> TracerProvider:
    """Initialize OpenTelemetry tracing with OTLP exporter."""
    global _trace_provider, _tracer
    
    if _trace_provider is not None:
        return _trace_provider
    
    settings = get_settings()
    
    # Create resource with service info
    resource = Resource.create({
        "service.name": "shop-desk",
        "service.version": "1.0.0",
        "deployment.environment": os.getenv("ENVIRONMENT", "development"),
    })
    
    _trace_provider = TracerProvider(resource=resource)
    
    # Add console exporter for development
    _trace_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    
    # Add OTLP exporter if endpoint configured
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint:
        otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
        _trace_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    
    trace.set_tracer_provider(_trace_provider)
    _tracer = trace.get_tracer("shop-desk")
    
    return _trace_provider


def get_tracer() -> Tracer:
    """Get the tracer instance, initializing if needed."""
    if _tracer is None:
        init_tracing()
    return _tracer


def get_current_session_id() -> Optional[str]:
    return _current_session_id.get()


def set_current_session_id(session_id: str) -> None:
    _current_session_id.set(session_id)


def get_current_trace_id() -> Optional[int]:
    return _current_trace_id.get()


def set_current_trace_id(trace_id: int) -> None:
    _current_trace_id.set(trace_id)


def get_current_span() -> Optional[Span]:
    return _current_span.get()


def set_current_span(span: Optional[Span]) -> None:
    _current_span.set(span)


def create_session_trace_id() -> int:
    """Create a new trace ID (16-byte hex as int)."""
    return uuid.uuid4().int & ((1 << 128) - 1)


def start_session_trace(session_id: str, metadata: Optional[dict] = None) -> tuple[Span, int]:
    """Start a new trace for a conversation session. Returns (span, trace_id)."""
    tracer = get_tracer()
    trace_id = create_session_trace_id()
    
    # Create span context with our trace ID
    span_context = SpanContext(
        trace_id=trace_id,
        span_id=uuid.uuid4().int & ((1 << 64) - 1),
        is_remote=False,
        trace_flags=TraceFlags(0x01),  # sampled
    )
    
    span = tracer.start_span(
        name="conversation.session",
        context=trace.set_span_in_context(trace.NonRecordingSpan(span_context)),
        attributes={
            "session.id": session_id,
            "session.trace_id": format(trace_id, '032x'),
            **(metadata or {}),
        },
    )
    
    set_current_session_id(session_id)
    set_current_trace_id(trace_id)
    set_current_span(span)
    
    return span, trace_id


def start_turn_span(turn_number: int, agent: str, model: str, path: str) -> Span:
    """Start a span for a single turn within the session."""
    tracer = get_tracer()
    parent_span = get_current_span()
    
    context = trace.set_span_in_context(parent_span) if parent_span else None
    
    span = tracer.start_span(
        name=f"conversation.turn.{turn_number}",
        context=context,
        attributes={
            "turn.number": turn_number,
            "turn.agent": agent,
            "turn.model": model,
            "turn.path": path,
            "session.id": get_current_session_id() or "unknown",
        },
    )
    
    set_current_span(span)
    return span


def end_turn_span(
    span: Span,
    tokens_prompt: int = 0,
    tokens_completion: int = 0,
    tokens_total: int = 0,
    cost_usd: float = 0.0,
    error: Optional[str] = None,
) -> None:
    """End a turn span with token/cost data."""
    span.set_attributes({
        "tokens.prompt": tokens_prompt,
        "tokens.completion": tokens_completion,
        "tokens.total": tokens_total,
        "cost.usd": cost_usd,
    })
    if error:
        span.set_attribute("error", True)
        span.set_attribute("error.message", error)
    span.end()


def end_session_trace(span: Span, summary: Optional[dict] = None) -> None:
    """End the session trace with summary."""
    if summary:
        span.set_attributes({
            "session.total_turns": summary.get("total_turns", 0),
            "session.total_tokens": summary.get("total_tokens", 0),
            "session.total_cost_usd": summary.get("total_cost_usd", 0.0),
            "session.fast_path_turns": summary.get("fast_path_turns", 0),
            "session.reasoning_path_turns": summary.get("reasoning_path_turns", 0),
        })
    span.end()
    
    # Clear context vars
    set_current_span(None)
    set_current_trace_id(None)
    set_current_session_id(None)


class TraceContext:
    """Context manager for turn-level tracing."""
    
    def __init__(self, turn_number: int, agent: str, model: str, path: str):
        self.turn_number = turn_number
        self.agent = agent
        self.model = model
        self.path = path
        self.span: Optional[Span] = None
    
    def __enter__(self) -> Span:
        self.span = start_turn_span(self.turn_number, self.agent, self.model, self.path)
        return self.span
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.span:
            if exc_type:
                end_turn_span(self.span, error=str(exc_val))
            else:
                end_turn_span(self.span)


def trace_turn(turn_number: int, agent: str, model: str, path: str) -> TraceContext:
    """Create a trace context for a turn."""
    return TraceContext(turn_number, agent, model, path)