import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from agents import RunConfig, RunResult, Runner

LEDGER_PATH = Path("ledger.jsonl")

_original_runner_run: Callable[..., Awaitable[RunResult]] | None = None
_registered = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_entry(
    *,
    request_id: str,
    agent: str,
    ms: float,
    findings: int,
    path: Path | str | None = None,
) -> dict[str, Any]:
    entry = {
        "ts": _now_iso(),
        "request_id": request_id,
        "agent": agent,
        "ms": round(ms, 3),
        "findings": findings,
    }
    target = Path(path) if path is not None else LEDGER_PATH
    with target.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read_ledger(path: Path | str | None = None) -> list[dict[str, Any]]:
    target = Path(path) if path is not None else LEDGER_PATH
    if not target.exists():
        return []
    entries: list[dict[str, Any]] = []
    with target.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def clear_ledger(path: Path | str | None = None) -> None:
    target = Path(path) if path is not None else LEDGER_PATH
    if target.exists():
        target.unlink()


def is_registered() -> bool:
    return _registered


async def _ledger_runner_run(
    starting_agent,
    input,
    *,
    context=None,
    max_turns=None,
    hooks=None,
    run_config=None,
    error_handlers=None,
    previous_response_id=None,
    auto_previous_response_id=False,
    conversation_id=None,
    session=None,
    **kwargs,
) -> RunResult:
    global _original_runner_run
    if _original_runner_run is None:
        raise RuntimeError("Ledger runner not initialized against original Runner.run")

    started = time.perf_counter()
    request_id = f"req_{uuid.uuid4().hex}"

    result = await _original_runner_run(
        starting_agent,
        input,
        context=context,
        max_turns=max_turns,
        hooks=hooks,
        run_config=run_config,
        error_handlers=error_handlers,
        previous_response_id=previous_response_id,
        auto_previous_response_id=auto_previous_response_id,
        conversation_id=conversation_id,
        session=session,
        **kwargs,
    )

    ms = (time.perf_counter() - started) * 1000
    output = result.final_output
    findings = len(output) if isinstance(output, list) else 0
    agent_name = getattr(result.last_agent, "name", "unknown")

    for resp in getattr(result, "raw_responses", None) or []:
        rid = getattr(resp, "request_id", None)
        if rid:
            request_id = rid
            break

    append_entry(
        request_id=request_id,
        agent=agent_name,
        ms=ms,
        findings=findings,
    )
    return result


def register_ledger() -> None:
    """Enable ledger logging. Sole toggle: call this once at startup."""
    global _original_runner_run, _registered
    if _registered:
        return
    _original_runner_run = Runner.run
    Runner.run = staticmethod(_ledger_runner_run)
    _registered = True


def unregister_ledger() -> None:
    """Disable ledger logging. Sole toggle: remove registration."""
    global _original_runner_run, _registered
    if not _registered:
        return
    if _original_runner_run is not None:
        Runner.run = _original_runner_run
    _original_runner_run = None
    _registered = False
