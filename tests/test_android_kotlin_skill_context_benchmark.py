"""Tests for Android Kotlin skill context optimization benchmark."""

from __future__ import annotations

from pathlib import Path

import yaml

from experiments.skill_context_optimization import benchmark_android_kotlin_context as bench


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DIGEST_PATH = (
    PROJECT_ROOT
    / "experiments"
    / "skill_context_optimization"
    / "android_kotlin_digest.yaml"
)
ZIP_PATH = Path("/Users/admin/Downloads/mobile-local-skills-pack-v1.1.1.zip")


def test_estimate_tokens_uses_four_character_heuristic() -> None:
    assert bench.estimate_tokens("") == 0
    assert bench.estimate_tokens("abcd") == 1
    assert bench.estimate_tokens("abcde") == 2


def test_render_digest_includes_agent_ready_sections() -> None:
    data = yaml.safe_load(DIGEST_PATH.read_text(encoding="utf-8"))

    rendered = bench.render_digest(data)

    assert "Agent Contract" in rendered
    assert "Must Follow" in rendered
    assert "Workflow" in rendered
    assert "Review Checks" in rendered
    assert "Anti-patterns" in rendered
    assert "{'" not in rendered


def test_audit_retains_all_required_hard_rules() -> None:
    audit = bench.build_audit(PROJECT_ROOT, ZIP_PATH, DIGEST_PATH)

    retention = audit["hard_rule_retention"]
    assert retention["hard_rule_retention_percent"] == 100.0
    assert retention["missing_rules"] == []


def test_audit_passes_context_optimization_thresholds() -> None:
    audit = bench.build_audit(PROJECT_ROOT, ZIP_PATH, DIGEST_PATH)

    assert audit["status"] == "pass"
    assert audit["variants"]["yaml_digest"]["reduction_vs_full_percent"] >= 50
    assert audit["variants"]["yaml_digest_delta"]["reduction_vs_full_percent"] >= 85


def test_build_gpt_agent_request_uses_digest_and_android_task() -> None:
    data = yaml.safe_load(DIGEST_PATH.read_text(encoding="utf-8"))
    digest_text = bench.render_digest(data)

    payload = bench.build_gpt_agent_request(
        digest_text=digest_text,
        user_task="Review a Kotlin Android RecyclerView state bug.",
        model="gpt-5",
        max_output_tokens=900,
    )

    assert payload["model"] == "gpt-5"
    assert payload["max_output_tokens"] == 900
    assert "local Kotlin Android skill digest" in payload["instructions"]
    assert "Review a Kotlin Android RecyclerView state bug." in payload["input"]
    assert "## Must Follow" in payload["input"]


def test_send_gpt_agent_request_requires_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = bench.send_gpt_agent_request({"model": "gpt-5", "input": "hello"})

    assert result["status"] == "skipped"
    assert "OPENAI_API_KEY" in result["reason"]


def test_truncate_process_output_bounds_noisy_logs() -> None:
    text, original_chars, truncated = bench._truncate_process_output("a" * 12, limit=10)

    assert original_chars == 12
    assert truncated is True
    assert "truncated 2 chars" in text
    assert len(text) > 10


def test_build_codex_cli_prompt_contains_digest_and_task() -> None:
    payload = {
        "instructions": "Use local skill digest.",
        "input": "<local_skill_digest>digest</local_skill_digest>\n<task>Fix RecyclerView</task>",
    }

    prompt = bench.build_codex_cli_prompt(payload)

    assert "Use local skill digest." in prompt
    assert "<local_skill_digest>digest</local_skill_digest>" in prompt
    assert "Fix RecyclerView" in prompt


def test_run_codex_cli_proxy_builds_safe_command(monkeypatch, tmp_path) -> None:
    calls = {}

    class _Result:
        returncode = 0
        stdout = "stdout text"
        stderr = ""

    def _fake_run(command, **kwargs):
        calls["command"] = command
        calls["kwargs"] = kwargs
        output_index = command.index("--output-last-message") + 1
        Path(command[output_index]).write_text("codex response", encoding="utf-8")
        return _Result()

    monkeypatch.setattr(bench.subprocess, "run", _fake_run)

    result = bench.run_codex_cli_proxy(
        {"instructions": "i", "input": "task"},
        output_dir=tmp_path,
        cwd=PROJECT_ROOT,
    )

    assert result["status"] == "success"
    assert result["stdout_chars"] == len("stdout text")
    assert result["stderr_truncated"] is False
    assert calls["command"][:2] == ["codex", "exec"]
    assert "--ephemeral" in calls["command"]
    assert "--sandbox" in calls["command"]
    assert "read-only" in calls["command"]
    assert "-m" not in calls["command"]
    assert "--ask-for-approval" not in calls["command"]
    assert calls["kwargs"]["input"] == "i\n\n task"


def test_run_codex_cli_proxy_accepts_explicit_cli_model(monkeypatch, tmp_path) -> None:
    calls = {}

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def _fake_run(command, **kwargs):
        calls["command"] = command
        output_index = command.index("--output-last-message") + 1
        Path(command[output_index]).write_text("codex response", encoding="utf-8")
        return _Result()

    monkeypatch.setattr(bench.subprocess, "run", _fake_run)

    result = bench.run_codex_cli_proxy(
        {"instructions": "i", "input": "task"},
        output_dir=tmp_path,
        cwd=PROJECT_ROOT,
        model="gpt-4.1",
    )

    assert result["status"] == "success"
    model_index = calls["command"].index("-m")
    assert calls["command"][model_index + 1] == "gpt-4.1"


def test_write_council_verdict_records_four_rounds(tmp_path) -> None:
    audit = bench.build_audit(PROJECT_ROOT, ZIP_PATH, DIGEST_PATH)

    bench.write_council_verdict(
        audit,
        {"status": "dry_run"},
        {"status": "success", "response_chars": 1000, "stderr_truncated": True},
        tmp_path,
    )

    verdict = (tmp_path / "android_kotlin_council_verdict.md").read_text(encoding="utf-8")

    assert "Final verdict: `accept`" in verdict
    assert "Round 1 - Context Budget" in verdict
    assert "Round 2 - Safety And Rule Retention" in verdict
    assert "Round 3 - Tool Integration" in verdict
    assert "Round 4 - Agent Usability" in verdict
