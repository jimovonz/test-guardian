"""Tests for prompts.py — verify prompt construction includes all required elements."""

import prompts


# Verifies: Phase 1 prompt includes prescriptive criteria, threat framing, scepticism warning, and the diff
def test_write_tests_prompt_structure():
    prompt = prompts.build_write_tests(
        diff="+ function handlePush(msg) {",
        static_findings="No static check findings.",
        scope_mode="diff",
    )
    # Prescriptive criteria
    assert "assert on behaviour" in prompt.lower() or "Assert on behaviour" in prompt
    assert "integration paths" in prompt.lower()
    assert "Mock only external boundaries" in prompt or "mock only external boundaries" in prompt.lower()
    # Threat framing
    assert "3rd party" in prompt or "independent" in prompt
    assert "assessor" in prompt or "examiner" in prompt
    # Scepticism warning
    assert "LLMs consistently underdeliver" in prompt
    assert "shortcut" in prompt.lower()
    # Comment requirement
    assert "Verifies:" in prompt
    # Diff included
    assert "handlePush" in prompt
    # TEST-GUARDIAN tag
    assert "TEST-GUARDIAN" in prompt


# Verifies: Phase 1 prompt uses file list instead of diff when scope is --all
def test_write_tests_all_mode():
    prompt = prompts.build_write_tests(
        diff="test/foo.test.ts\nsrc/foo.ts",
        static_findings="No static check findings.",
        scope_mode="all",
    )
    assert "Files in scope" in prompt or "files" in prompt.lower()
    assert "foo.test.ts" in prompt


# Verifies: Phase 1 prompt includes static findings when present
def test_write_tests_includes_static_findings():
    findings = "- [CRITICAL] test.ts:5 — Tautological assertion"
    prompt = prompts.build_write_tests(
        diff="+ some code",
        static_findings=findings,
        scope_mode="diff",
    )
    assert "Tautological assertion" in prompt


# Verifies: Phase 2 prompt asks for structured JSON with complete/remaining fields
def test_confirm_complete_structure():
    prompt = prompts.build_confirm_complete()
    assert '"complete"' in prompt
    assert '"remaining"' in prompt
    assert "prescribed standard" in prompt.lower()
    # Comment check included
    assert "Verifies:" in prompt


# Verifies: Phase 3 prompt includes threat of examination, scepticism about false confidence, and JSON format
def test_confident_of_pass_structure():
    prompt = prompts.build_confident_of_pass()
    assert "assessor" in prompt or "examiner" in prompt
    assert '"confident"' in prompt
    assert '"gaps"' in prompt
    assert "false confidence" in prompt.lower()
    assert "documented tendency" in prompt.lower()


# Verifies: lint gate prompt includes the findings text and asks for fixes
def test_lint_gate_includes_findings():
    findings = "- [WARNING] test.ts:10 — Missing comment"
    prompt = prompts.build_lint_gate(findings)
    assert "Missing comment" in prompt
    assert "static checker" in prompt.lower() or "Static Check" in prompt


# Verifies: comment validation prompt includes test samples and asks for mismatch JSON
def test_comment_validation_structure():
    samples = "File: test.ts:5\n// Verifies: foo works\ntest('foo', () => {\nAssertions:\n  expect(result).toBeDefined()"
    prompt = prompts.build_comment_validation(samples)
    assert "foo works" in prompt
    assert '"mismatches"' in prompt
    assert "comment" in prompt.lower()
    assert "assertion" in prompt.lower()


# Verifies: JSON enforcement prompt includes the previous response and demands only JSON output
def test_json_enforcement_structure():
    prompt = prompts.build_json_enforcement("I think the tests look good overall.")
    assert "I think the tests look good" in prompt
    assert '"confident"' in prompt
    assert '"gaps"' in prompt
    assert "No prose" in prompt or "nothing else" in prompt.lower()
