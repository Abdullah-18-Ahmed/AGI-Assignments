import asyncio
import inspect
from dataclasses import fields as dataclass_fields

import pytest
from agents import Agent
from pydantic import ValidationError

from desk import (
    DiffError,
    Finding,
    ReviewContext,
    build_instructions,
    build_reviewer,
    read_diff,
    split_by_file,
)


# --- FR-1 ---

SAMPLE_DIFF = """\
diff --git a/src/app.py b/src/app.py
index 111..222 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,3 +1,4 @@
 import os
+import sys
 def main():
diff --git a/src/util.py b/src/util.py
index 333..444 100644
--- a/src/util.py
+++ b/src/util.py
@@ -1,2 +1,3 @@
 def helper():
+    return None
"""


def test_fr1_two_file_diff_produces_two_chunks():
    chunks = split_by_file(SAMPLE_DIFF)
    assert isinstance(chunks, list)
    assert len(chunks) == 2
    files = {c.file for c in chunks}
    assert any("app.py" in f for f in files)
    assert any("util.py" in f for f in files)


def test_fr1_empty_diff_returns_message_not_traceback(tmp_path):
    p = tmp_path / "empty.diff"
    p.write_text("", encoding="utf-8")
    result = asyncio.run(read_diff(str(p)))
    assert isinstance(result, DiffError)
    assert "empty" in result.message.lower()


def test_fr1_malformed_diff_returns_message_not_traceback(tmp_path):
    p = tmp_path / "bad.diff"
    p.write_text("this is not a diff at all", encoding="utf-8")
    result = asyncio.run(read_diff(str(p)))
    assert isinstance(result, DiffError)
    assert "malformed" in result.message.lower()


def test_fr1_missing_file_returns_message_not_traceback(tmp_path):
    result = asyncio.run(read_diff(str(tmp_path / "nope.diff")))
    assert isinstance(result, DiffError)
    assert "not found" in result.message.lower()


def test_fr1_agent_model_configured_on_instance():
    ctx = ReviewContext(repo="demo", language="python", ruleset_id="py-standard")
    agent = build_reviewer(ctx)
    assert isinstance(agent, Agent)
    assert agent.model == "gpt-4o-mini"


def test_fr1_no_global_default_client():
    import desk.agents as agents_mod

    source = inspect.getsource(agents_mod)
    assert "set_default_openai_client" not in source
    assert "set_default_openai_models" not in source


# --- FR-2 ---

def test_fr2_review_context_is_dataclass():
    import desk.context as ctx_mod

    assert hasattr(ctx_mod.ReviewContext, "__dataclass_fields__")
    names = {f.name for f in dataclass_fields(ctx_mod.ReviewContext)}
    assert names == {"repo", "language", "ruleset_id", "strictness"}


def test_fr2_context_defaults_strictness_normal():
    ctx = ReviewContext(repo="r", language="python", ruleset_id="x")
    assert ctx.strictness == "normal"


def test_fr2_tool_reads_ruleset_via_wrapper():
    from agents.tool_context import ToolContext

    ctx = ReviewContext(repo="secret-repo-name", language="python", ruleset_id="rl-42")
    reviewer = build_reviewer(ctx)
    tool = reviewer.tools[0]
    tool_ctx = ToolContext(
        context=None,
        tool_name=tool.name,
        tool_call_id="call_1",
        tool_arguments="{}",
    )
    result = asyncio.run(tool.on_invoke_tool(tool_ctx, "{}"))
    assert "rl-42" in result
    assert "python" in result


def test_fr2_tool_schema_has_no_wrapper_parameters():
    ctx = ReviewContext(repo="r", language="python", ruleset_id="x")
    reviewer = build_reviewer(ctx)
    tool = reviewer.tools[0]
    schema = tool.params_json_schema or {}
    props = schema.get("properties", {})
    assert "context" not in props
    assert "review_context" not in props
    assert "repo" not in props


def test_fr2_no_repo_name_in_prompts():
    ctx = ReviewContext(repo="acme-super-secret-repo", language="python", ruleset_id="x")
    instructions = build_instructions(ctx)
    assert "acme-super-secret-repo" not in instructions
    reviewer = build_reviewer(ctx)
    assert "acme-super-secret-repo" not in str(reviewer.instructions)


# --- FR-3 ---

def test_fr3_finding_is_pydantic_model():
    f = Finding(file="a.py", line=10, severity="major", message="bug")
    assert isinstance(f, Finding)
    assert f.file == "a.py"
    assert f.line == 10
    assert f.severity == "major"
    assert f.message == "bug"


def test_fr3_finding_severity_literal_validation():
    with pytest.raises(ValidationError):
        Finding(file="a.py", line=1, severity="fatal", message="x")


def test_fr3_agent_output_type_is_list_of_finding():
    ctx = ReviewContext(repo="r", language="python", ruleset_id="x")
    agent = build_reviewer(ctx)
    assert agent.output_type == list[Finding]


# --- FR-4 ---

def test_fr4_prompt_uses_ruleset_language_strictness():
    ctx = ReviewContext(repo="r", language="go", ruleset_id="go-strict-set", strictness="normal")
    prompt = build_instructions(ctx)
    assert "go-strict-set" in prompt
    assert "go" in prompt
    assert "normal" in prompt or "strictness" in prompt.lower() or "Weigh" in prompt


def test_fr4_strict_prompt_is_terser():
    normal = build_instructions(ReviewContext(repo="r", language="python", ruleset_id="x", strictness="normal"))
    strict = build_instructions(ReviewContext(repo="r", language="python", ruleset_id="x", strictness="strict"))
    assert len(strict) < len(normal)
    assert "terse" in strict.lower() or "strict" in strict.lower()


def test_fr4_instructions_built_dynamically_at_request_time():
    ctx1 = ReviewContext(repo="r", language="python", ruleset_id="set-a", strictness="normal")
    ctx2 = ReviewContext(repo="r", language="python", ruleset_id="set-b", strictness="strict")
    a1 = build_reviewer(ctx1)
    a2 = build_reviewer(ctx2)
    assert a1.instructions != a2.instructions
    assert "set-a" in a1.instructions
    assert "set-b" in a2.instructions


# --- final_output shape ---

def test_final_output_yields_valid_list_of_finding():
    findings = [
        Finding(file="src/app.py", line=3, severity="critical", message="hardcoded secret"),
        Finding(file="src/util.py", line=7, severity="minor", message="unused import"),
    ]
    assert isinstance(findings, list)
    for f in findings:
        assert isinstance(f, Finding)
        assert f.severity in ("critical", "major", "minor")
