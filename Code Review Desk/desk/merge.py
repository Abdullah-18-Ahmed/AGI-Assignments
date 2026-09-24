from desk.findings import Finding, MergedReport, RemediationProposal

SEVERITY_ORDER = {"critical": 0, "major": 1, "minor": 2}


def has_critical_finding(findings: list[Finding]) -> bool:
    return any(f.severity == "critical" for f in findings)


def merge_findings(
    security: list[Finding],
    tests: list[Finding],
    style: list[Finding],
    *,
    reviewers_completed: list[str] | None = None,
    slowest_reviewer: str | None = None,
) -> MergedReport:
    seen: set[tuple[str, int, str]] = set()
    merged: list[Finding] = []

    for group in (security, tests, style):
        for finding in group:
            key = (finding.file, finding.line, finding.message)
            if key in seen:
                continue
            seen.add(key)
            merged.append(finding)

    merged.sort(key=lambda f: SEVERITY_ORDER.get(f.severity, 99))

    completed = reviewers_completed or ["SecurityReviewer", "TestReviewer", "StyleReviewer"]
    critical_count = sum(1 for f in merged if f.severity == "critical")
    summary = (
        f"{len(merged)} findings "
        f"({critical_count} critical) from {len(completed)} reviewers"
    )

    return MergedReport(
        findings=merged,
        reviewers_completed=completed,
        slowest_reviewer=slowest_reviewer,
        summary=summary,
    )


def build_proposal(finding: Finding, patch: str, rationale: str) -> RemediationProposal:
    return RemediationProposal(finding=finding, patch=patch, rationale=rationale)
