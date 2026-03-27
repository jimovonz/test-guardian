"""Tests for prompts.py — verify prompt construction includes all required elements."""

import prompts


# --- Phase 1: build_write_tests ---

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
    assert "files" in prompt.lower() or "Files" in prompt
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


# Verifies: Phase 1 prompt wraps diff in code block for diff mode but not all mode
def test_write_tests_diff_mode_code_block():
    prompt = prompts.build_write_tests(
        diff="+ added line",
        static_findings="No findings.",
        scope_mode="diff",
    )
    assert "```diff" in prompt


# Verifies: Phase 1 prompt does NOT wrap scope in diff code block for all mode
def test_write_tests_all_mode_no_diff_block():
    prompt = prompts.build_write_tests(
        diff="test/foo.test.ts\nsrc/foo.ts",
        static_findings="No findings.",
        scope_mode="all",
    )
    assert "```diff" not in prompt


# Verifies: Phase 1 prompt includes context reset preamble to prevent session bleed
def test_write_tests_context_reset():
    prompt = prompts.build_write_tests(
        diff="+ code",
        static_findings="No findings.",
        scope_mode="diff",
    )
    assert "Context Reset" in prompt
    assert "forked specifically" in prompt
    assert "Ignore all prior conversation" in prompt


# Verifies: Phase 1 prompt includes error/edge case requirement
def test_write_tests_error_cases():
    prompt = prompts.build_write_tests(
        diff="+ code",
        static_findings="No findings.",
        scope_mode="diff",
    )
    assert "error" in prompt.lower() and "edge" in prompt.lower()


# --- Phase 2: build_confirm_complete ---

# Verifies: Phase 2 prompt asks for structured JSON with complete/remaining fields
def test_confirm_complete_structure():
    prompt = prompts.build_confirm_complete()
    assert '"complete"' in prompt
    assert '"remaining"' in prompt
    assert "prescribed standard" in prompt.lower()
    # Comment check included
    assert "Verifies:" in prompt


# Verifies: Phase 2 prompt asks the session to self-review against specific criteria
def test_confirm_complete_self_review():
    prompt = prompts.build_confirm_complete()
    assert "non-trivial code path" in prompt
    assert "existence/type" in prompt.lower() or "existence" in prompt.lower()
    assert "integration paths" in prompt.lower()
    assert "mocks only at external boundaries" in prompt.lower() or "Mock" in prompt


# Verifies: Phase 2 prompt warns about gaps being caught in next stage
def test_confirm_complete_honest_warning():
    prompt = prompts.build_confirm_complete()
    assert "honest" in prompt.lower() or "Gaps you miss" in prompt


# --- Phase 3: build_confident_of_pass ---

# Verifies: Phase 3 prompt includes threat of examination, scepticism about false confidence, and JSON format
def test_confident_of_pass_structure():
    prompt = prompts.build_confident_of_pass()
    assert "assessor" in prompt or "examiner" in prompt
    assert '"confident"' in prompt
    assert '"gaps"' in prompt
    assert "false confidence" in prompt.lower()
    assert "documented tendency" in prompt.lower()


# Verifies: Phase 3 prompt describes what the assessor will check
def test_confident_of_pass_assessor_checks():
    prompt = prompts.build_confident_of_pass()
    assert "tautological" in prompt.lower()
    assert "integration" in prompt.lower()
    assert "error path" in prompt.lower()
    assert "mock" in prompt.lower()


# --- Lint gate ---

# Verifies: lint gate prompt includes the findings text and asks for fixes
def test_lint_gate_includes_findings():
    findings = "- [WARNING] test.ts:10 — Missing comment"
    prompt = prompts.build_lint_gate(findings)
    assert "Missing comment" in prompt
    assert "static checker" in prompt.lower() or "Static Check" in prompt


# Verifies: lint gate prompt demands fixes before proceeding
def test_lint_gate_demands_fixes():
    prompt = prompts.build_lint_gate("- [CRITICAL] issue")
    assert "fix" in prompt.lower() or "Fix" in prompt
    assert "resolved" in prompt.lower() or "must" in prompt.lower()


# --- Comment validation ---

# Verifies: comment validation prompt includes test samples and asks for mismatch JSON
def test_comment_validation_structure():
    samples = "File: test.ts:5\n// Verifies: foo works\ntest('foo', () => {\nAssertions:\n  expect(result).toBeDefined()"
    prompt = prompts.build_comment_validation(samples)
    assert "foo works" in prompt
    assert '"mismatches"' in prompt
    assert "comment" in prompt.lower()
    assert "assertion" in prompt.lower()


# Verifies: comment validation prompt describes what constitutes a mismatch
def test_comment_validation_mismatch_criteria():
    prompt = prompts.build_comment_validation("sample data")
    assert "claims more than" in prompt or "comment claims" in prompt
    assert "vague" in prompt.lower() or "generic" in prompt.lower()


# --- JSON enforcement ---

# Verifies: JSON enforcement prompt includes the previous response and demands only JSON output
def test_json_enforcement_structure():
    prompt = prompts.build_json_enforcement("I think the tests look good overall.")
    assert "I think the tests look good" in prompt
    assert '"confident"' in prompt
    assert '"gaps"' in prompt
    assert "No prose" in prompt or "nothing else" in prompt.lower()


# Verifies: JSON enforcement prompt truncates long previous responses at 300 characters
def test_json_enforcement_truncation():
    long_response = "A" * 500
    prompt = prompts.build_json_enforcement(long_response)
    # Should contain only 300 chars of the response
    assert "A" * 300 in prompt
    assert "A" * 301 not in prompt


# Verifies: JSON enforcement prompt does NOT truncate short responses
def test_json_enforcement_no_truncation_short():
    short_response = "Brief response."
    prompt = prompts.build_json_enforcement(short_response)
    assert "Brief response." in prompt


# Verifies: JSON enforcement provides both JSON format options (confident true and false)
def test_json_enforcement_both_formats():
    prompt = prompts.build_json_enforcement("whatever")
    assert '"confident": true' in prompt
    assert '"confident": false' in prompt
