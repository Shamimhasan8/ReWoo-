"""OpenTelemetry distributed tracing integration for ReWoo.

Provides end-to-end distributed tracing with support for:
- OTLP exporters (HTTP and gRPC)
- FastAPI request instrumentation
- SQLAlchemy query instrumentation
- Redis operation instrumentation
- HTTPX client instrumentation
- Celery task instrumentation
- Custom span processors for request_id and user_id attribution

All instrumentation is guarded by try/except ImportError so that the
application works correctly even when opentelemetry packages are not installed.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Track whether tracing was successfully initialized
_tracing_initialized: bool = False
_tracer_provider: Any = None

# ---------------------------------------------------------------------------
# Graceful no-op helpers when opentelemetry is not installed
# ---------------------------------------------------------------------------

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME
    from opentelemetry.sdk.trace.sampling import ParentBasedTraceIdRatio

    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False

    # Provide minimal stubs so that call-sites don't need their own guards
    class _StubTracer:  # type: ignore[no-redef]
        def start_span(self, *a: Any, **kw: Any) -> Any:
            return _StubSpan()

        def start_as_current_span(self, *a: Any, **kw: Any) -> Any:
            from contextlib import contextmanager

            @contextmanager
            def _ctx():
                yield _StubSpan()

            return _ctx()

    class _StubSpan:  # type: ignore[no-redef]
        def __enter__(self) -> "_StubSpan":
            return self

        def __exit__(self, *a: Any) -> None:
            pass

        def set_attribute(self, *a: Any, **kw: Any) -> None:
            pass

        def add_event(self, *a: Any, **kw: Any) -> None:
            pass

        def record_exception(self, *a: Any, **kw: Any) -> None:
            pass

        def is_recording(self) -> bool:
            return False

        @property
        def context(self) -> None:
            return None

    trace = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Custom span processors
# ---------------------------------------------------------------------------

if _HAS_OTEL:
    from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor
    from opentelemetry.context import Context

    class RequestIDSpanProcessor(SpanProcessor):
        """Adds rewoo.request_id attribute to every span.

        The request_id is read from a thread-local/context-var that is set
        by the RequestIDMiddleware so that every child span within a request
        carries the same request_id.
        """

        _current_request_id: str | None = None

        def on_start(
            self, span: Any, parent_context: Context | None = None
        ) -> None:
            if self._current_request_id:
                span.set_attribute("rewoo.request_id", self._current_request_id)

        def on_end(self, span: ReadableSpan) -> None:
            pass

        def shutdown(self) -> None:
            pass

        def force_flush(self, timeout_millis: int = 30000) -> bool:
            return True

    class UserIDSpanProcessor(SpanProcessor):
        """Adds rewoo.user_id attribute to every span.

        Similar to RequestIDSpanProcessor but for the authenticated user.
        """

        _current_user_id: str | None = None

        def on_start(
            self, span: Any, parent_context: Context | None = None
        ) -> None:
            if self._current_user_id:
                span.set_attribute("rewoo.user_id", self._current_user_id)

        def on_end(self, span: ReadableSpan) -> None:
            pass

        def shutdown(self) -> None:
            pass

        def force_flush(self, timeout_millis: int = 30000) -> bool:
            return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def setup_tracing(
    app_name: str = "rewoo",
    endpoint: Optional[str] = None,
    headers: Optional[dict[str, str]] = None,
) -> bool:
    """Initialize OpenTelemetry tracing pipeline.

    Configures:
    - Resource with service name
    - OTLP exporter (HTTP or gRPC depending on endpoint scheme)
    - BatchSpanProcessor for efficient export
    - Custom RequestIDSpanProcessor and UserIDSpanProcessor
    - FastAPI, SQLAlchemy, Redis, HTTPX, and Celery auto-instrumentation

    Args:
        app_name: Service name used in the telemetry resource.
        endpoint: OTLP collector endpoint URL. If the URL starts with
            ``http`` an OTLP/HTTP exporter is used; otherwise gRPC.
        headers: Optional dict of headers sent with every OTLP export request.

    Returns:
        True if tracing was initialized successfully, False otherwise.
    """
    global _tracing_initialized, _tracer_provider  # noqa: PLW0603

    if _tracing_initialized:
        logger.debug("Tracing already initialized — skipping")
        return True

    if not _HAS_OTEL:
        logger.info(
            "opentelemetry packages not installed — distributed tracing disabled"
        )
        return False

    # Resolve endpoint from argument → env var → default
    endpoint = endpoint or os.environ.get("REWOO_OTEL_ENDPOINT")
    headers = headers or _parse_headers_env()

    if not endpoint:
        logger.info("No OTLP endpoint configured — distributed tracing disabled")
        return False

    try:
        # --- Resource ---
        resource = Resource.create({SERVICE_NAME: app_name})

        # --- Sampler ---
        # Sample 100% by default; override via REWOO_OTEL_SAMPLING_RATE (0.0–1.0)
        sampling_rate = float(os.environ.get("REWOO_OTEL_SAMPLING_RATE", "1.0"))
        sampler = ParentBasedTraceIdRatio(rate=sampling_rate)

        # --- TracerProvider ---
        provider = TracerProvider(resource=resource, sampler=sampler)

        # --- Exporter ---
        _configure_exporter(provider, endpoint, headers)

        # --- Custom span processors ---
        provider.add_span_processor(RequestIDSpanProcessor())
        provider.add_span_processor(UserIDSpanProcessor())

        # --- Set global tracer provider ---
        trace.set_tracer_provider(provider)
        _tracer_provider = provider

        # --- Auto-instrumentation ---
        _instrument_fastapi()
        _instrument_sqlalchemy()
        _instrument_redis()
        _instrument_httpx()
        _instrument_celery()

        _tracing_initialized = True
        logger.info(
            "OpenTelemetry tracing initialized (service=%s, endpoint=%s)",
            app_name,
            endpoint,
        )
        return True

    except Exception:
        logger.exception("Failed to initialize OpenTelemetry tracing")
        return False


def shutdown_tracing() -> None:
    """Gracefully shut down the tracing pipeline.

    Flushes pending spans and shuts down the tracer provider.
    """
    global _tracing_initialized, _tracer_provider  # noqa: PLW0603

    if not _tracing_initialized or _tracer_provider is None:
        return

    try:
        _tracer_provider.shutdown()  # type: ignore[union-attr]
        logger.info("OpenTelemetry tracing shut down gracefully")
    except Exception:
        logger.exception("Error shutting down OpenTelemetry tracing")
    finally:
        _tracing_initialized = False
        _tracer_provider = None


def get_tracer(name: str = "rewoo") -> Any:
    """Return an OpenTelemetry tracer (or a no-op stub).

    Use this whenever you need to create custom spans::

        from rewoo.monitoring.tracing import get_tracer

        tracer = get_tracer(__name__)
        with tracer.start_as_current_span("my_operation"):
            ...
    """
    if _HAS_OTEL and _tracing_initialized:
        return trace.get_tracer(name)  # type: ignore[union-attr]
    return _StubTracer()


def set_request_id(request_id: str) -> None:
    """Set the current request_id on the custom span processors."""
    if _HAS_OTEL and _tracing_initialized:
        # Update the class-level variable so all new spans pick it up
        RequestIDSpanProcessor._current_request_id = request_id


def set_user_id(user_id: str) -> None:
    """Set the current user_id on the custom span processors."""
    if _HAS_OTEL and _tracing_initialized:
        UserIDSpanProcessor._current_user_id = user_id


def clear_context() -> None:
    """Clear request_id and user_id from span processors (end of request)."""
    if _HAS_OTEL:
        RequestIDSpanProcessor._current_request_id = None
        UserIDSpanProcessor._current_user_id = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_headers_env() -> dict[str, str]:
    """Parse REWOO_OTEL_HEADERS env var into a dict.

    Expected format: ``key1=value1,key2=value2``
    """
    raw = os.environ.get("REWOO_OTEL_HEADERS", "")
    if not raw:
        return {}
    headers: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if "=" in pair:
            k, v = pair.split("=", 1)
            headers[k.strip()] = v.strip()
    return headers


def _configure_exporter(
    provider: "TracerProvider",  # type: ignore[name-defined]
    endpoint: str,
    headers: dict[str, str] | None,
) -> None:
    """Create and attach the appropriate OTLP exporter to the provider."""
    headers = headers or {}

    if endpoint.startswith("http://") or endpoint.startswith("https://"):
        # OTLP/HTTP exporter
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )
        except ImportError:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # type: ignore[no-redef]
                OTLPSpanExporter,
            )

        exporter = OTLPSpanExporter(endpoint=endpoint, headers=headers)
    else:
        # OTLP/gRPC exporter (default)
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
        except ImportError:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # type: ignore[no-redef]
                OTLPSpanExporter,
            )

        exporter = OTLPSpanExporter(endpoint=endpoint, headers=headers)

    provider.add_span_processor(BatchSpanProcessor(exporter))


def _instrument_fastapi() -> None:
    """Instrument FastAPI if the instrumentation package is available."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument()  # type: ignore[no-untyped-call]
        logger.debug("FastAPI instrumentation enabled")
    except ImportError:
        logger.debug("opentelemetry-instrumentation-fastapi not installed — skipped")
    except Exception:
        logger.exception("Failed to instrument FastAPI")


def _instrument_sqlalchemy() -> None:
    """Instrument SQLAlchemy if the instrumentation package is available."""
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor.instrument()  # type: ignore[no-untyped-call]
        logger.debug("SQLAlchemy instrumentation enabled")
    except ImportError:
        logger.debug("opentelemetry-instrumentation-sqlalchemy not installed — skipped")
    except Exception:
        logger.exception("Failed to instrument SQLAlchemy")


def _instrument_redis() -> None:
    """Instrument Redis if the instrumentation package is available."""
    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor

        RedisInstrumentor.instrument()  # type: ignore[no-untyped-call]
        logger.debug("Redis instrumentation enabled")
    except ImportError:
        logger.debug("opentelemetry-instrumentation-redis not installed — skipped")
    except Exception:
        logger.exception("Failed to instrument Redis")


def _instrument_httpx() -> None:
    """Instrument HTTPX if the instrumentation package is available."""
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor.instrument()  # type: ignore[no-untyped-call]
        logger.debug("HTTPX instrumentation enabled")
    except ImportError:
        logger.debug("opentelemetry-instrumentation-httpx not installed — skipped")
    except Exception:
        logger.exception("Failed to instrument HTTPX")


def _instrument_celery() -> None:
    """Instrument Celery if the instrumentation package is available."""
    try:
        from opentelemetry.instrumentation.celery import CeleryInstrumentor

        CeleryInstrumentor.instrument()  # type: ignore[no-untyped-call]
        logger.debug("Celery instrumentation enabled")
    except ImportError:
        logger.debug("opentelemetry-instrumentation-celery not installed — skipped")
    except Exception:
        logger.exception("Failed to instrument Celery")
