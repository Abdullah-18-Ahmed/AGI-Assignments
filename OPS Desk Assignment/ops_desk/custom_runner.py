"""FR-11 — custom runner: request id + elapsed time around every run; register once."""

from __future__ import annotations

import time
import uuid
from typing import Any

from agents.run import AgentRunner, set_default_agent_runner

from ops_desk.audit import RECORDER

_registered = False


class StampedRunner(AgentRunner):
    """Wraps every Runner.run / run_sync / run_streamed with request_id + elapsed_ms.

    Agent definitions are untouched — registration is process-level only (FR-11).
    """

    async def run(self, starting_agent: Any, input: Any, **kwargs: Any) -> Any:
        request_id = uuid.uuid4().hex
        started = time.perf_counter()
        agent_name = getattr(starting_agent, "name", "?")
        RECORDER.record(
            "runner_start",
            agent_name,
            request_id=request_id,
            scope="custom_runner",
        )
        try:
            result = await super().run(starting_agent, input, **kwargs)
        finally:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            RECORDER.record(
                "runner_end",
                agent_name,
                request_id=request_id,
                elapsed_ms=elapsed_ms,
                scope="custom_runner",
            )
            # Visible stamp on stdout for demo / viva
            print(
                f"[custom-runner] request_id={request_id} "
                f"agent={agent_name} elapsed_ms={elapsed_ms}"
            )
        # Attach stamps for callers that want them (result is SDK object; use side channel)
        if hasattr(result, "__dict__"):
            try:
                result.request_id = request_id  # type: ignore[attr-defined]
                result.elapsed_ms = elapsed_ms  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001 — never break the run for stamping
                pass
        return result

    def run_sync(self, starting_agent: Any, input: Any, **kwargs: Any) -> Any:
        request_id = uuid.uuid4().hex
        started = time.perf_counter()
        agent_name = getattr(starting_agent, "name", "?")
        RECORDER.record(
            "runner_start",
            agent_name,
            request_id=request_id,
            scope="custom_runner",
            mode="sync",
        )
        result = super().run_sync(starting_agent, input, **kwargs)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        RECORDER.record(
            "runner_end",
            agent_name,
            request_id=request_id,
            elapsed_ms=elapsed_ms,
            scope="custom_runner",
            mode="sync",
        )
        print(
            f"[custom-runner] request_id={request_id} "
            f"agent={agent_name} elapsed_ms={elapsed_ms}"
        )
        if hasattr(result, "__dict__"):
            try:
                result.request_id = request_id  # type: ignore[attr-defined]
                result.elapsed_ms = elapsed_ms  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass
        return result


def register_custom_runner(force: bool = False) -> StampedRunner:
    """Register once at startup (FR-11). Idempotent."""
    global _registered
    if _registered and not force:
        existing = None
        from agents.run import get_default_agent_runner

        existing = get_default_agent_runner()
        if isinstance(existing, StampedRunner):
            return existing
    runner = StampedRunner()
    set_default_agent_runner(runner)
    _registered = True
    return runner


def is_custom_runner_registered() -> bool:
    from agents.run import get_default_agent_runner

    return isinstance(get_default_agent_runner(), StampedRunner)
