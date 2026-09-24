from typing import Literal

from pydantic import BaseModel


class Finding(BaseModel):
    file: str
    line: int
    severity: Literal["critical", "major", "minor"]
    message: str


class MergedReport(BaseModel):
    findings: list[Finding]
    reviewers_completed: list[str] = []
    slowest_reviewer: str | None = None
    summary: str = ""


class RemediationProposal(BaseModel):
    finding: Finding
    patch: str
    rationale: str
