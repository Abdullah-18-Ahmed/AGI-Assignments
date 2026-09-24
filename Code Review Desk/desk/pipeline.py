import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from agents import (
    Agent,
    ItemHelpers,
    MaxTurnsExceeded,
    MessageOutputItem,
    OutputGuardrailTripwireTriggered,
    RunConfig,
    RunErrorHandlerInput,
    RunErrorHandlerResult,
    Runner,
    RunResult,
    ToolCallOutputItem,
    set_tracing_disabled,
)

from desk.agents import (
    build_desk_host,
    build_merge_agent,
    build_remediation_agent,
    build_security_reviewer,
    build_style_reviewer,
    build_test_reviewer,
)
from desk.context import ReviewContext
from desk.diff_reader import DiffError, FileChunk, read_diff, split_by_file
from desk.findings import Finding, MergedReport, RemediationProposal
from desk.guardrails import extract_secrets
from desk.hooks import MetricsRunHooks, ReviewerMetrics, attach_agent_metrics
from desk.ledger import append_entry, is_registered
from desk.merge import has_critical_finding, merge_findings
from desk.otel import reviewer_span, review_trace

RunnerFn = Callable[..., Awaitable[RunResult]]
FindingsCallback = Callable[[str, list[Finding]], Awaitable[None]]


@dataclass
class ReviewOutcome:
    status: str
    findings: list[Finding] = field(default_factory=list)
    report: MergedReport | None = None
    remediation: RemediationProposal | None = None
    message: str = ""
    partial: bool = False
    elapsed_ms: float = 0.0
    slowest_reviewer: str | None = None
    results: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, ReviewerMetrics] = field(default_factory=dict)
    metrics_footer: str = ""
    trace_id: str | None = None


def _salvage_findings_from_run_data(run_data) -> list[Finding]:
    findings: list[Finding] = []
    texts: list[str] = []

    for response in getattr(run_data, "raw_responses", []) or []:
        output = getattr(response, "output", None) or []
        for item in output:
            try:
                text = ItemHelpers.extract_last_text(item)
            except Exception:
                text = None
            if text:
                texts.append(text)

    for item in getattr(run_data, "new_items", []) or []:
        if isinstance(item, MessageOutputItem):
            try:
                texts.append(ItemHelpers.text_message_output(item))
            except Exception:
                pass
        elif isinstance(item, ToolCallOutputItem):
            out = getattr(item, "output", None)
            if isinstance(out, str):
                texts.append(out)

    for text in texts:
        if not text:
            continue
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(data, list):
            continue
        for raw in data:
            try:
                findings.append(Finding(**raw))
            except Exception:
                continue

    deduped: dict[tuple[str, int, str], Finding] = {}
    for f in findings:
        deduped[(f.file, f.line, f.message)] = f
    return list(deduped.values())


def make_max_turns_handler(partial_sink: dict) -> Callable[[RunErrorHandlerInput], Any]:
    def handler(inp: RunErrorHandlerInput) -> RunErrorHandlerResult:
        partial_sink["truncated"] = True
        findings = _salvage_findings_from_run_data(inp.run_data)
        partial_sink["findings"] = findings
        return RunErrorHandlerResult(final_output=findings, include_in_history=False)

    return handler


def _extract_findings(result: Any) -> list[Finding]:
    output = getattr(result, "final_output", None)
    if isinstance(output, list):
        findings: list[Finding] = []
        for item in output:
            if isinstance(item, Finding):
                findings.append(item)
            elif isinstance(item, dict):
                try:
                    findings.append(Finding(**item))
                except Exception:
                    continue
        return findings
    return []


async def run_reviewer(
    agent: Agent,
    chunk_text: str,
    context: ReviewContext,
    *,
    max_turns: int = 10,
    model_override: str | None = None,
    run_config: RunConfig | None = None,
    runner: RunnerFn | None = None,
    partial_sink: dict | None = None,
    hooks=None,
) -> RunResult:
    run = runner or Runner.run
    if run_config is None and model_override:
        run_config = RunConfig(model=model_override)

    kwargs: dict[str, Any] = {
        "context": context,
        "max_turns": max_turns,
    }
    if run_config is not None:
        kwargs["run_config"] = run_config
    if partial_sink is not None:
        kwargs["error_handlers"] = {"max_turns": make_max_turns_handler(partial_sink)}
    if hooks is not None:
        kwargs["hooks"] = hooks

    t0 = time.perf_counter()
    result = await run(agent, chunk_text, **kwargs)
    if runner is not None and is_registered():
        ms = (time.perf_counter() - t0) * 1000
        try:
            output = result.final_output
            findings = len(output) if isinstance(output, list) else 0
            agent_name = getattr(result.last_agent, "name", agent.name)
            request_id = f"req_{id(result):x}"
            for resp in getattr(result, "raw_responses", None) or []:
                rid = getattr(resp, "request_id", None)
                if rid:
                    request_id = rid
                    break
            append_entry(request_id=request_id, agent=agent_name, ms=ms, findings=findings)
        except Exception:
            pass
    return result


async def run_reviewers_concurrently(
    agents: list[Agent],
    chunk_text: str,
    context: ReviewContext,
    *,
    max_turns: int = 10,
    model_override: str | None = None,
    runner: RunnerFn | None = None,
    hooks=None,
    on_findings: FindingsCallback | None = None,
) -> dict[str, Any]:
    sinks: dict[str, dict] = {a.name: {"truncated": False, "findings": []} for a in agents}
    started = time.perf_counter()

    async def _one(agent: Agent) -> tuple[str, RunResult | BaseException]:
        sink = sinks[agent.name]
        try:
            with reviewer_span(agent.name):
                result = await run_reviewer(
                    agent,
                    chunk_text,
                    context,
                    max_turns=max_turns,
                    model_override=model_override,
                    runner=runner,
                    partial_sink=sink,
                    hooks=hooks,
                )
            if on_findings is not None:
                findings = _extract_findings(result)
                await on_findings(agent.name, findings)
            return agent.name, result
        except BaseException as e:
            return agent.name, e

    pairs = await asyncio.gather(*[_one(a) for a in agents])
    elapsed_ms = (time.perf_counter() - started) * 1000

    by_name: dict[str, RunResult | BaseException] = dict(pairs)
    timings: dict[str, float] = {}
    return {
        "by_name": by_name,
        "sinks": sinks,
        "elapsed_ms": elapsed_ms,
        "timings": timings,
    }


async def _safe_run(
    agent: Agent,
    inp: Any,
    context: ReviewContext,
    *,
    max_turns: int = 10,
    model_override: str | None = None,
    runner: RunnerFn | None = None,
    hooks=None,
) -> RunResult | str:
    run = runner or Runner.run
    run_config = RunConfig(model=model_override) if model_override else None
    kwargs: dict[str, Any] = {"context": context, "max_turns": max_turns}
    if run_config is not None:
        kwargs["run_config"] = run_config
    if hooks is not None:
        kwargs["hooks"] = hooks

    t0 = time.perf_counter()
    try:
        result = await run(agent, inp, **kwargs)
    except OutputGuardrailTripwireTriggered as e:
        return f"refused: {e}"
    except MaxTurnsExceeded as e:
        return f"partial: {e}"

    if runner is not None and is_registered():
        ms = (time.perf_counter() - t0) * 1000
        try:
            output = result.final_output
            findings = len(output) if isinstance(output, list) else 0
            agent_name = getattr(result.last_agent, "name", agent.name)
            request_id = f"req_{id(result):x}"
            for resp in getattr(result, "raw_responses", None) or []:
                rid = getattr(resp, "request_id", None)
                if rid:
                    request_id = rid
                    break
            append_entry(request_id=request_id, agent=agent_name, ms=ms, findings=findings)
        except Exception:
            pass
    return result


async def run_pipeline(
    diff_path: str,
    context: ReviewContext,
    *,
    max_turns: int = 10,
    model_override: str | None = None,
    runner: RunnerFn | None = None,
    tracing_disabled: bool = True,
    on_findings: FindingsCallback | None = None,
    enable_otel: bool = True,
) -> ReviewOutcome:
    if not enable_otel:
        if tracing_disabled:
            set_tracing_disabled(True)
    else:
        set_tracing_disabled(False)

    metrics_hooks = MetricsRunHooks()
    otel_span = None
    otel_cm = None

    started = time.perf_counter()

    diff_text = await read_diff(diff_path)
    if isinstance(diff_text, DiffError):
        return ReviewOutcome(status="error", message=diff_text.message)

    chunks = split_by_file(diff_text)
    if isinstance(chunks, DiffError):
        return ReviewOutcome(status="error", message=chunks.message)

    combined = "\n".join(c.content for c in chunks)
    secrets = extract_secrets(diff_text)

    remediation = build_remediation_agent(context, secrets=secrets)
    security = build_security_reviewer(context, secrets=secrets, remediation=remediation)
    test = build_test_reviewer(context, secrets=secrets)
    style = build_style_reviewer(context, secrets=secrets)
    merge_agent = build_merge_agent(context, secrets=secrets)
    desk_host = build_desk_host(context, merge_agent, secrets=secrets)

    reviewers = [security, test, style]
    shared_store: dict[str, ReviewerMetrics] = {}
    attach_agent_metrics([security], shared_store)

    if enable_otel:
        try:
            from desk.otel import configure_opentelemetry, is_configured

            if not is_configured():
                configure_opentelemetry()
            otel_cm = review_trace(diff_path)
            otel_span = otel_cm.__enter__()
        except Exception:
            otel_cm = None
            otel_span = None

    try:
        fanout = await run_reviewers_concurrently(
            reviewers,
            combined,
            context,
            max_turns=max_turns,
            model_override=model_override,
            runner=runner,
            hooks=metrics_hooks,
            on_findings=on_findings,
        )

        by_name = fanout["by_name"]
        sinks = fanout["sinks"]
        elapsed_ms = fanout["elapsed_ms"]

        findings_by_reviewer: dict[str, list[Finding]] = {}
        errors: list[str] = []
        completed: list[str] = []

        for agent in reviewers:
            name = agent.name
            outcome = by_name.get(name)
            if isinstance(outcome, OutputGuardrailTripwireTriggered):
                return ReviewOutcome(
                    status="refused",
                    message=f"output guardrail refused {name}: {outcome}",
                    elapsed_ms=elapsed_ms,
                    metrics=metrics_hooks.metrics,
                    metrics_footer=metrics_hooks.footer(),
                )
            if isinstance(outcome, BaseException):
                errors.append(f"{name}: {type(outcome).__name__}: {outcome}")
                if sinks.get(name, {}).get("truncated"):
                    findings_by_reviewer[name] = sinks[name].get("findings", [])
                    completed.append(name)
                continue
            if isinstance(outcome, str) and outcome.startswith("refused:"):
                return ReviewOutcome(
                    status="refused",
                    message=outcome,
                    elapsed_ms=elapsed_ms,
                    metrics=metrics_hooks.metrics,
                    metrics_footer=metrics_hooks.footer(),
                )
            if isinstance(outcome, str) and outcome.startswith("partial:"):
                findings_by_reviewer[agent.name] = sinks.get(agent.name, {}).get("findings", [])
                completed.append(agent.name)
                errors.append(f"{agent.name}: {outcome}")
                continue
            if hasattr(outcome, "final_output") and not isinstance(outcome, BaseException):
                final_output = getattr(outcome, "final_output", None)
                try:
                    if isinstance(final_output, str) and final_output.startswith("refused:"):
                        return ReviewOutcome(
                            status="refused",
                            message=final_output,
                            elapsed_ms=elapsed_ms,
                            metrics=metrics_hooks.metrics,
                            metrics_footer=metrics_hooks.footer(),
                        )
                except Exception:
                    pass
                findings = _extract_findings(outcome)
                sink = sinks.get(name, {})
                if sink.get("truncated"):
                    findings = sink.get("findings") or findings
                    errors.append(f"{name}: partial review (max turns)")
                findings_by_reviewer[name] = findings
                completed.append(name)
                metrics_hooks.metrics.setdefault(
                    name, ReviewerMetrics(agent=name)
                ).findings_count = len(findings)

        if errors and not completed:
            return ReviewOutcome(
                status="error",
                message="; ".join(errors),
                elapsed_ms=elapsed_ms,
                metrics=metrics_hooks.metrics,
                metrics_footer=metrics_hooks.footer(),
            )

        sec = findings_by_reviewer.get("SecurityReviewer", [])
        tst = findings_by_reviewer.get("TestReviewer", [])
        stl = findings_by_reviewer.get("StyleReviewer", [])

        report = merge_findings(sec, tst, stl, reviewers_completed=completed)

        with reviewer_span("Merge"):
            merge_input = json.dumps(
                {
                    "SecurityReviewer": [f.model_dump() for f in sec],
                    "TestReviewer": [f.model_dump() for f in tst],
                    "StyleReviewer": [f.model_dump() for f in stl],
                }
            )
            merge_result = await _safe_run(
                desk_host,
                merge_input,
                context,
                max_turns=max_turns,
                model_override=model_override,
                runner=runner,
                hooks=metrics_hooks,
            )
        if isinstance(merge_result, str) and merge_result.startswith("refused:"):
            return ReviewOutcome(
                status="refused",
                message=merge_result,
                elapsed_ms=elapsed_ms,
                metrics=metrics_hooks.metrics,
                metrics_footer=metrics_hooks.footer(),
            )
        if hasattr(merge_result, "final_output") and not isinstance(merge_result, BaseException):
            merged_findings = _extract_findings(merge_result)
            if merged_findings:
                report = merge_findings(
                    merged_findings,
                    [],
                    [],
                    reviewers_completed=completed,
                )

        remediation_result = None
        if has_critical_finding(sec):
            critical = next(f for f in sec if f.severity == "critical")
            # FR-6: remediation is reached by handoff from SecurityReviewer.
            # Start the run on security (which has handoffs=[handoff(remediation)])
            # so the specialist takes over the conversation.
            with reviewer_span("Remediation"):
                handoff_input = (
                    "A critical security finding requires remediation. "
                    "Hand off to the Remediation agent now with this finding: "
                    f"{critical.model_dump_json()}"
                )
                remediation_result = await _safe_run(
                    security,
                    handoff_input,
                    context,
                    max_turns=max_turns,
                    model_override=model_override,
                    runner=runner,
                    hooks=metrics_hooks,
                )
            if isinstance(remediation_result, str) and remediation_result.startswith("refused:"):
                return ReviewOutcome(
                    status="refused",
                    message=remediation_result,
                    elapsed_ms=elapsed_ms,
                    metrics=metrics_hooks.metrics,
                    metrics_footer=metrics_hooks.footer(),
                )

        proposal = None
        if hasattr(remediation_result, "final_output") and not isinstance(
            remediation_result, BaseException
        ):
            out = remediation_result.final_output
            if isinstance(out, RemediationProposal):
                proposal = out
            elif isinstance(out, dict):
                try:
                    proposal = RemediationProposal(**out)
                except Exception:
                    proposal = None

        partial = any(sinks.get(a.name, {}).get("truncated") for a in reviewers)
        status = "partial" if partial else "ok"
        message = "; ".join(errors) if errors else "review complete"

        all_findings = report.findings
        for name, flist in findings_by_reviewer.items():
            slot = metrics_hooks.metrics.setdefault(name, ReviewerMetrics(agent=name))
            if not slot.findings_count:
                slot.findings_count = len(flist)

        metrics_hooks.metrics.update(
            {k: v for k, v in shared_store.items() if k not in metrics_hooks.metrics}
        )
        for k, v in shared_store.items():
            if k in metrics_hooks.metrics:
                m = metrics_hooks.metrics[k]
                if v.elapsed_ms > 0 and m.elapsed_ms == 0:
                    m.ms = v.elapsed_ms
                    m.start_perf = v.start_perf
                    m.end_perf = v.end_perf
                if v.total_tokens and not m.total_tokens:
                    m.input_tokens = v.input_tokens
                    m.output_tokens = v.output_tokens
                    m.total_tokens = v.total_tokens
                    m.requests = v.requests
                if v.findings_count and not m.findings_count:
                    m.findings_count = v.findings_count

        if metrics_hooks.metrics:
            times = {
                k: m.elapsed_ms
                for k, m in metrics_hooks.metrics.items()
                if m.elapsed_ms > 0
                and k in ("SecurityReviewer", "TestReviewer", "StyleReviewer")
            }
            if times:
                slowest = max(times, key=times.get)
            else:
                slowest = None
        else:
            slowest = None

        trace_id = None
        if otel_span is not None:
            try:
                ctx = otel_span.get_span_context()
                trace_id = format(ctx.trace_id, "032x")
            except Exception:
                trace_id = None

        footer = metrics_hooks.footer()
        return ReviewOutcome(
            status=status,
            findings=all_findings,
            report=report,
            remediation=proposal,
            message=message,
            partial=partial,
            elapsed_ms=elapsed_ms,
            slowest_reviewer=slowest,
            results={"fanout": {k: type(v).__name__ for k, v in by_name.items()}},
            metrics=dict(metrics_hooks.metrics),
            metrics_footer=footer,
            trace_id=trace_id,
        )
    finally:
        if otel_cm is not None:
            try:
                otel_cm.__exit__(None, None, None)
            except Exception:
                pass


async def measure_wall_clock(
    agents: list[Agent],
    chunk_text: str,
    context: ReviewContext,
    *,
    runner: RunnerFn,
    sequential_runner: RunnerFn | None = None,
    max_turns: int = 10,
) -> dict[str, float]:
    seq_run = sequential_runner or runner

    t0 = time.perf_counter()
    for agent in agents:
        await run_reviewer(agent, chunk_text, context, max_turns=max_turns, runner=seq_run)
    sequential_ms = (time.perf_counter() - t0) * 1000

    concurrent = await run_reviewers_concurrently(
        agents, chunk_text, context, max_turns=max_turns, runner=runner
    )

    return {
        "sequential_ms": sequential_ms,
        "concurrent_ms": concurrent["elapsed_ms"],
        "speedup": sequential_ms / concurrent["elapsed_ms"]
        if concurrent["elapsed_ms"] > 0
        else 0.0,
    }
