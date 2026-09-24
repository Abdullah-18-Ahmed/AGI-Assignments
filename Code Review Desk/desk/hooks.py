import time
from dataclasses import dataclass, field

from agents import AgentHooks, RunHooks
from agents.items import ModelResponse


@dataclass
class ReviewerMetrics:
    agent: str
    start_perf: float | None = None
    end_perf: float | None = None
    ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    requests: int = 0
    request_ids: list[str] = field(default_factory=list)
    findings_count: int = 0

    @property
    def elapsed_ms(self) -> float:
        if self.start_perf is not None and self.end_perf is not None:
            return (self.end_perf - self.start_perf) * 1000
        return self.ms


class MetricsRunHooks(RunHooks):
    """Run-level hooks measuring latency and tokens per reviewer."""

    def __init__(self) -> None:
        self.metrics: dict[str, ReviewerMetrics] = {}
        self._run_start = time.perf_counter()

    def _slot(self, agent_name: str) -> ReviewerMetrics:
        if agent_name not in self.metrics:
            self.metrics[agent_name] = ReviewerMetrics(agent=agent_name)
        return self.metrics[agent_name]

    async def on_agent_start(self, context, agent) -> None:
        slot = self._slot(agent.name)
        slot.start_perf = time.perf_counter()

    async def on_agent_end(self, context, agent, output) -> None:
        slot = self._slot(agent.name)
        slot.end_perf = time.perf_counter()
        slot.ms = slot.elapsed_ms
        if isinstance(output, list):
            slot.findings_count = len(output)
        usage = getattr(context, "usage", None)
        if usage is not None:
            slot.input_tokens = usage.input_tokens
            slot.output_tokens = usage.output_tokens
            slot.total_tokens = usage.total_tokens
            slot.requests = usage.requests

    async def on_llm_end(self, context, agent: "Agent", response: ModelResponse) -> None:
        slot = self._slot(agent.name)
        if response.request_id:
            slot.request_ids.append(response.request_id)
        usage = response.usage
        if usage is not None:
            slot.input_tokens += usage.input_tokens
            slot.output_tokens += usage.output_tokens
            slot.total_tokens += usage.total_tokens
            slot.requests = max(slot.requests, usage.requests)

    def total_ms(self) -> float:
        return (time.perf_counter() - self._run_start) * 1000

    def total_tokens(self) -> int:
        return sum(m.total_tokens for m in self.metrics.values())

    def footer(self) -> str:
        lines = [
            "",
            "---",
            "### Review metrics",
            "",
            "| Agent | Latency (ms) | Input tokens | Output tokens | Total tokens | Requests | Findings |",
            "|-------|-------------:|-------------:|--------------:|-------------:|---------:|---------:|",
        ]
        for name in ("SecurityReviewer", "TestReviewer", "StyleReviewer", "Merge", "Remediation"):
            m = self.metrics.get(name)
            if m is None:
                continue
            lines.append(
                f"| {m.agent} | {m.elapsed_ms:.0f} | {m.input_tokens} | "
                f"{m.output_tokens} | {m.total_tokens} | {m.requests} | {m.findings_count} |"
            )
        for name, m in self.metrics.items():
            if name in ("SecurityReviewer", "TestReviewer", "StyleReviewer", "Merge", "Remediation"):
                continue
            lines.append(
                f"| {m.agent} | {m.elapsed_ms:.0f} | {m.input_tokens} | "
                f"{m.output_tokens} | {m.total_tokens} | {m.requests} | {m.findings_count} |"
            )
        lines.append(
            f"| **Total** | **{self.total_ms():.0f}** | | | **{self.total_tokens()}** | | |"
        )
        return "\n".join(lines)


class MetricsAgentHooks(AgentHooks):
    """Agent-level hooks for per-agent latency when attached to a single agent."""

    def __init__(self, agent_name: str, store: dict[str, ReviewerMetrics]) -> None:
        self.agent_name = agent_name
        self.store = store

    def _slot(self) -> ReviewerMetrics:
        if self.agent_name not in self.store:
            self.store[self.agent_name] = ReviewerMetrics(agent=self.agent_name)
        return self.store[self.agent_name]

    async def on_start(self, context, agent) -> None:
        self._slot().start_perf = time.perf_counter()

    async def on_end(self, context, agent, output) -> None:
        slot = self._slot()
        slot.end_perf = time.perf_counter()
        slot.ms = slot.elapsed_ms
        if isinstance(output, list):
            slot.findings_count = len(output)
        usage = getattr(context, "usage", None)
        if usage is not None:
            slot.input_tokens = usage.input_tokens
            slot.output_tokens = usage.output_tokens
            slot.total_tokens = usage.total_tokens
            slot.requests = usage.requests


def attach_agent_metrics(agents: list, store: dict[str, ReviewerMetrics]) -> None:
    for agent in agents:
        agent.hooks = MetricsAgentHooks(agent.name, store)
