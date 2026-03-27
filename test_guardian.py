"""Tests for guardian.py — JSON extraction, ForkSession, get_diff, and main orchestration."""

import json
import subprocess
from unittest.mock import patch, MagicMock

import static_checks
from guardian import extract_json, ForkSession, get_diff, main


# --- JSON extraction ---

# Verifies: extract_json parses a raw JSON object from plain text
def test_extract_json_raw():
    text = 'Some text before {"complete": true, "summary": "all done"} some text after'
    result = extract_json(text)
    assert result == {"complete": True, "summary": "all done"}


# Verifies: extract_json parses JSON from a markdown code block
def test_extract_json_code_block():
    text = """Here are my findings:

```json
{"confident": false, "gaps": ["missing dedup test"]}
```

I will fix these now."""
    result = extract_json(text)
    assert result == {"confident": False, "gaps": ["missing dedup test"]}


# Verifies: extract_json prefers code block JSON over raw JSON when both are present
def test_extract_json_prefers_code_block():
    text = """Some {"noise": true} before

```json
{"confident": true}
```"""
    result = extract_json(text)
    assert result == {"confident": True}


# Verifies: extract_json returns None when no valid JSON is found
def test_extract_json_no_json():
    result = extract_json("No JSON here at all")
    assert result is None


# Verifies: extract_json returns None for malformed JSON rather than raising
def test_extract_json_malformed():
    result = extract_json('{"broken": }')
    assert result is None


# Verifies: extract_json handles the complete:true response from Phase 2
def test_extract_json_phase2_complete():
    text = '```json\n{"complete": true, "summary": "Added 12 tests covering all integration paths"}\n```'
    result = extract_json(text)
    assert result["complete"] is True
    assert "integration" in result["summary"]


# Verifies: extract_json handles the complete:false response with remaining work list
def test_extract_json_phase2_incomplete():
    text = '{"complete": false, "remaining": ["error path for handlePush", "geofence boundary test"]}'
    result = extract_json(text)
    assert result["complete"] is False
    assert len(result["remaining"]) == 2


# Verifies: extract_json handles the confident:true response from Phase 3
def test_extract_json_phase3_confident():
    text = '```json\n{"confident": true}\n```'
    result = extract_json(text)
    assert result["confident"] is True


# Verifies: extract_json handles the confident:false response with gaps list from Phase 3
def test_extract_json_phase3_gaps():
    text = """I found some remaining issues:

```json
{"confident": false, "gaps": ["no test for email dedup flow", "mock DB not verified"]}
```"""
    result = extract_json(text)
    assert result["confident"] is False
    assert len(result["gaps"]) == 2


# Verifies: extract_json handles the mismatches response from comment validation gate
def test_extract_json_comment_validation():
    text = '{"mismatches": ["test.ts:42 — comment claims dedup but assertion only checks toBeDefined"]}'
    result = extract_json(text)
    assert len(result["mismatches"]) == 1


# Verifies: extract_json handles code block without json language tag
def test_extract_json_code_block_no_lang():
    text = """```
{"confident": true}
```"""
    result = extract_json(text)
    assert result == {"confident": True}


# Verifies: extract_json returns None for malformed JSON inside a code block
def test_extract_json_malformed_in_code_block():
    text = '```json\n{"broken: true}\n```'
    result = extract_json(text)
    # Falls through to raw JSON search, which also fails
    assert result is None


# Verifies: extract_json handles empty string input without raising
def test_extract_json_empty_string():
    result = extract_json("")
    assert result is None


# --- ForkSession ---

# Verifies: ForkSession.__init__ sets default state correctly — no session_id, empty responses
def test_fork_session_init():
    session = ForkSession()
    assert session.session_id is None
    assert session.permission_mode == "bypassPermissions"
    assert session.responses == []


# Verifies: ForkSession.__init__ accepts custom permission mode
def test_fork_session_custom_permission():
    session = ForkSession(permission_mode="auto")
    assert session.permission_mode == "auto"


# Verifies: ForkSession.send captures session_id from first response and uses --resume on subsequent calls
def test_fork_session_send_captures_session_id():
    session = ForkSession()
    mock_output = json.dumps({"session_id": "abc-123", "result": "tests written"})

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=mock_output,
            stderr="",
        )
        response = session.send("write tests")

    assert session.session_id == "abc-123"
    assert response == "tests written"
    assert len(session.responses) == 1

    # Verify first call does NOT use --resume
    first_call_args = mock_run.call_args[0][0]
    assert "--resume" not in first_call_args
    assert "write tests" in first_call_args


# Verifies: ForkSession.send uses --resume with session_id on subsequent calls
def test_fork_session_send_resumes():
    session = ForkSession()
    session.session_id = "existing-session"
    mock_output = json.dumps({"session_id": "existing-session", "result": "continued"})

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=mock_output,
            stderr="",
        )
        response = session.send("continue work")

    call_args = mock_run.call_args[0][0]
    assert "--resume" in call_args
    assert "existing-session" in call_args
    assert response == "continued"


# Verifies: ForkSession.send raises RuntimeError on non-zero exit code with stderr message
def test_fork_session_send_error_stderr():
    session = ForkSession()

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Permission denied",
        )
        try:
            session.send("test prompt")
            assert False, "Should have raised RuntimeError"
        except RuntimeError as e:
            assert "exit 1" in str(e)
            assert "Permission denied" in str(e)


# Verifies: ForkSession.send raises RuntimeError using stdout when stderr is empty
def test_fork_session_send_error_stdout_fallback():
    session = ForkSession()

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="Error in stdout",
            stderr="",
        )
        try:
            session.send("test prompt")
            assert False, "Should have raised RuntimeError"
        except RuntimeError as e:
            assert "Error in stdout" in str(e)


# Verifies: ForkSession.send strips <memory> blocks from response text
def test_fork_session_strips_memory_blocks():
    response_with_memory = "Test results look good.\n<memory>\n- type: fact\n- topic: test\n</memory>"
    mock_output = json.dumps({"session_id": "s1", "result": response_with_memory})

    session = ForkSession()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=mock_output,
            stderr="",
        )
        response = session.send("check tests")

    assert "<memory>" not in response
    assert "Test results look good." in response


# Verifies: ForkSession.send includes --permission-mode flag in command
def test_fork_session_permission_mode_in_command():
    session = ForkSession(permission_mode="bypassPermissions")
    mock_output = json.dumps({"session_id": "s1", "result": "ok"})

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=mock_output,
            stderr="",
        )
        session.send("test")

    call_args = mock_run.call_args[0][0]
    assert "--permission-mode" in call_args
    idx = call_args.index("--permission-mode")
    assert call_args[idx + 1] == "bypassPermissions"


# Verifies: ForkSession.send passes timeout to subprocess.run
def test_fork_session_timeout():
    session = ForkSession()
    mock_output = json.dumps({"session_id": "s1", "result": "ok"})

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=mock_output,
            stderr="",
        )
        session.send("test")

    assert mock_run.call_args[1]["timeout"] == 600


# Verifies: ForkSession.send accumulates responses across multiple calls
def test_fork_session_accumulates_responses():
    session = ForkSession()

    responses = [
        json.dumps({"session_id": "s1", "result": "first"}),
        json.dumps({"session_id": "s1", "result": "second"}),
        json.dumps({"session_id": "s1", "result": "third"}),
    ]

    with patch("subprocess.run") as mock_run:
        for resp in responses:
            mock_run.return_value = MagicMock(returncode=0, stdout=resp, stderr="")
            session.send("prompt")

    assert len(session.responses) == 3
    assert session.responses == ["first", "second", "third"]


# --- get_diff ---

# Verifies: get_diff returns staged + unstaged diff by default (no base, no all_mode)
def test_get_diff_default():
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(stdout="staged changes\n", stderr=""),
            MagicMock(stdout="unstaged changes\n", stderr=""),
        ]
        result = get_diff()

    assert "staged changes" in result
    assert "unstaged changes" in result
    # Should make two calls: git diff --cached and git diff
    assert mock_run.call_count == 2
    first_call = mock_run.call_args_list[0][0][0]
    second_call = mock_run.call_args_list[1][0][0]
    assert "--cached" in first_call
    assert "--cached" not in second_call


# Verifies: get_diff uses git diff base...HEAD when base branch is specified
def test_get_diff_with_base():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="diff against main\n", stderr="")
        result = get_diff(base="main")

    assert "diff against main" in result
    call_args = mock_run.call_args[0][0]
    assert "main...HEAD" in call_args


# Verifies: get_diff in all_mode lists test files and source files separately
def test_get_diff_all_mode():
    file_list = "src/handler.ts\ntests/handler.test.ts\nREADME.md\n.gitignore\n"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=file_list, stderr="")
        result = get_diff(all_mode=True)

    assert "Test files:" in result
    assert "handler.test.ts" in result
    assert "Source files:" in result
    assert "handler.ts" in result
    assert "README.md" in result
    # Dotfiles excluded from source list
    assert ".gitignore" not in result


# Verifies: get_diff in all_mode returns empty string when no test files exist
def test_get_diff_all_mode_no_tests():
    file_list = "src/main.ts\nREADME.md\n"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=file_list, stderr="")
        result = get_diff(all_mode=True)

    assert result == ""


# Verifies: get_diff default mode returns empty string when both staged and unstaged diffs are empty
def test_get_diff_default_empty():
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(stdout="", stderr=""),
            MagicMock(stdout="", stderr=""),
        ]
        result = get_diff()

    assert result == ""


# --- main() integration ---

# Verifies: main() in --lint mode runs static_checks.lint and exits 0 when clean
def test_main_lint_mode_clean(capsys):
    with patch("static_checks.lint", return_value=[]), \
         patch("sys.argv", ["guardian.py", "--lint"]):
        try:
            main()
        except SystemExit as e:
            assert e.code == 0

    captured = capsys.readouterr()
    assert "CLEAN" in captured.out


# Verifies: main() in --lint mode exits 1 and shows findings count when issues found
def test_main_lint_mode_findings(capsys):
    from static_checks import Finding
    findings = [
        Finding(file="test.ts", line=1, rule="tautological-true",
                message="Tautological", severity="critical")
    ]
    with patch("static_checks.lint", return_value=findings), \
         patch("sys.argv", ["guardian.py", "--lint"]):
        try:
            main()
        except SystemExit as e:
            assert e.code == 1

    captured = capsys.readouterr()
    assert "1 finding(s)" in captured.out


# Verifies: main() exits with "No changes to review" when diff is empty and not in --all mode
def test_main_no_changes(capsys):
    with patch("guardian.get_diff", return_value=""), \
         patch("sys.argv", ["guardian.py"]):
        try:
            main()
        except SystemExit as e:
            assert e.code == 0

    captured = capsys.readouterr()
    assert "No changes to review" in captured.out


# Verifies: main() orchestrates all phases through ForkSession and produces a report
def test_main_full_orchestration(capsys):
    phase1_resp = json.dumps({"session_id": "s1", "result": "Wrote 5 tests."})
    phase2_resp = json.dumps({
        "session_id": "s1",
        "result": '```json\n{"complete": true, "summary": "all done"}\n```',
    })
    phase3_resp = json.dumps({
        "session_id": "s1",
        "result": '```json\n{"confident": true}\n```',
    })

    call_count = {"n": 0}
    responses = [phase1_resp, phase2_resp]

    def mock_subprocess_run(cmd, **kwargs):
        # Static checks calls (git ls-files for lint)
        if cmd[0] == "git":
            return MagicMock(stdout="", stderr="", returncode=0)
        # Claude calls
        resp = responses[call_count["n"]] if call_count["n"] < len(responses) else phase3_resp
        call_count["n"] += 1
        return MagicMock(stdout=resp, stderr="", returncode=0)

    with patch("subprocess.run", side_effect=mock_subprocess_run), \
         patch("guardian.get_diff", return_value="+ some diff"), \
         patch("static_checks.run", return_value=[]), \
         patch("static_checks.lint", return_value=[]), \
         patch("static_checks.collect_test_samples", return_value=""), \
         patch("sys.argv", ["guardian.py"]):
        main()

    captured = capsys.readouterr()
    assert "Test Guardian Report" in captured.out


# Verifies: main() with --max-iter 1 limits iteration count for phases 2 and 3
def test_main_max_iter_respected(capsys):
    phase1_resp = json.dumps({"session_id": "s1", "result": "Wrote tests."})
    # Phase 2: always incomplete — should only iterate once with --max-iter 1
    phase2_resp = json.dumps({
        "session_id": "s1",
        "result": '```json\n{"complete": false, "remaining": ["still more"]}\n```',
    })
    phase3_resp = json.dumps({
        "session_id": "s1",
        "result": '```json\n{"confident": false, "gaps": ["gap1"]}\n```',
    })

    call_count = {"n": 0}
    ordered = [phase1_resp, phase2_resp, phase3_resp]

    def mock_run(cmd, **kwargs):
        if cmd[0] == "git":
            return MagicMock(stdout="", stderr="", returncode=0)
        resp = ordered[min(call_count["n"], len(ordered) - 1)]
        call_count["n"] += 1
        return MagicMock(stdout=resp, stderr="", returncode=0)

    with patch("subprocess.run", side_effect=mock_run), \
         patch("guardian.get_diff", return_value="+ code"), \
         patch("static_checks.run", return_value=[]), \
         patch("static_checks.lint", return_value=[]), \
         patch("static_checks.collect_test_samples", return_value=""), \
         patch("sys.argv", ["guardian.py", "--max-iter", "1"]):
        main()

    captured = capsys.readouterr()
    assert "Test Guardian Report" in captured.out
    # With max-iter 1, phase 2 gets exactly 1 iteration
    assert "**Completion checks**: 1 iteration(s)" in captured.out


# Verifies: main() Phase 2.5 sends lint findings back to session, then passes on clean re-lint
def test_main_phase25_lint_then_pass(capsys):
    from static_checks import Finding

    phase1_resp = json.dumps({"session_id": "s1", "result": "Wrote tests."})
    phase2_resp = json.dumps({
        "session_id": "s1",
        "result": '```json\n{"complete": true, "summary": "done"}\n```',
    })
    lint_fix_resp = json.dumps({"session_id": "s1", "result": "Fixed lint issues."})
    phase3_resp = json.dumps({
        "session_id": "s1",
        "result": '```json\n{"confident": true}\n```',
    })

    call_count = {"n": 0}
    ordered = [phase1_resp, phase2_resp, lint_fix_resp, phase3_resp]

    def mock_run(cmd, **kwargs):
        if cmd[0] == "git":
            return MagicMock(stdout="", stderr="", returncode=0)
        resp = ordered[min(call_count["n"], len(ordered) - 1)]
        call_count["n"] += 1
        return MagicMock(stdout=resp, stderr="", returncode=0)

    lint_call_count = {"n": 0}
    lint_finding = Finding(file="test.ts", line=1, rule="tautological-true",
                           message="Tautological", severity="critical")

    def mock_lint(root="."):
        lint_call_count["n"] += 1
        # First call returns findings, second call returns clean
        if lint_call_count["n"] == 1:
            return [lint_finding]
        return []

    with patch("subprocess.run", side_effect=mock_run), \
         patch("guardian.get_diff", return_value="+ code"), \
         patch("static_checks.run", return_value=[]), \
         patch("static_checks.lint", side_effect=mock_lint), \
         patch("static_checks.collect_test_samples", return_value=""), \
         patch("sys.argv", ["guardian.py"]):
        main()

    captured = capsys.readouterr()
    assert "Test Guardian Report" in captured.out
    # Should show quality gate checks (lint iteration + pass)
    assert "**Quality gate checks**: 2 iteration(s)" in captured.out


# Verifies: main() Phase 2.5 handles comment validation mismatches then passes
def test_main_phase25_comment_validation_mismatches(capsys):
    phase1_resp = json.dumps({"session_id": "s1", "result": "Wrote tests."})
    phase2_resp = json.dumps({
        "session_id": "s1",
        "result": '```json\n{"complete": true, "summary": "done"}\n```',
    })
    # Comment validation finds mismatches first time
    validation_resp = json.dumps({
        "session_id": "s1",
        "result": '```json\n{"mismatches": ["test.ts:5 — comment claims X but checks Y"]}\n```',
    })
    phase3_resp = json.dumps({
        "session_id": "s1",
        "result": '```json\n{"confident": true}\n```',
    })

    call_count = {"n": 0}
    ordered = [phase1_resp, phase2_resp, validation_resp, phase3_resp]

    def mock_run(cmd, **kwargs):
        if cmd[0] == "git":
            return MagicMock(stdout="", stderr="", returncode=0)
        resp = ordered[min(call_count["n"], len(ordered) - 1)]
        call_count["n"] += 1
        return MagicMock(stdout=resp, stderr="", returncode=0)

    lint_call_count = {"n": 0}

    def mock_lint(root="."):
        return []  # Lint always clean

    samples_call_count = {"n": 0}

    def mock_samples(root="."):
        samples_call_count["n"] += 1
        if samples_call_count["n"] == 1:
            return "File: test.ts:5\n// Verifies: X\ntest('foo')\nAssertions:\n  expect(r).toBeDefined()"
        return ""  # No samples second time — gate passes

    with patch("subprocess.run", side_effect=mock_run), \
         patch("guardian.get_diff", return_value="+ code"), \
         patch("static_checks.run", return_value=[]), \
         patch("static_checks.lint", side_effect=mock_lint), \
         patch("static_checks.collect_test_samples", side_effect=mock_samples), \
         patch("sys.argv", ["guardian.py"]):
        main()

    captured = capsys.readouterr()
    assert "Test Guardian Report" in captured.out
    assert "Quality Gate" in captured.out


# Verifies: main() Phase 3 uses JSON enforcement when first response has no JSON, then succeeds
def test_main_phase3_json_enforcement(capsys):
    phase1_resp = json.dumps({"session_id": "s1", "result": "Wrote tests."})
    phase2_resp = json.dumps({
        "session_id": "s1",
        "result": '```json\n{"complete": true, "summary": "done"}\n```',
    })
    # Phase 3 first response: no JSON
    phase3_no_json = json.dumps({
        "session_id": "s1",
        "result": "I believe the tests are comprehensive.",
    })
    # Phase 3 second response: JSON after enforcement
    phase3_json = json.dumps({
        "session_id": "s1",
        "result": '```json\n{"confident": true}\n```',
    })

    call_count = {"n": 0}
    ordered = [phase1_resp, phase2_resp, phase3_no_json, phase3_json]

    def mock_run(cmd, **kwargs):
        if cmd[0] == "git":
            return MagicMock(stdout="", stderr="", returncode=0)
        resp = ordered[min(call_count["n"], len(ordered) - 1)]
        call_count["n"] += 1
        return MagicMock(stdout=resp, stderr="", returncode=0)

    with patch("subprocess.run", side_effect=mock_run), \
         patch("guardian.get_diff", return_value="+ code"), \
         patch("static_checks.run", return_value=[]), \
         patch("static_checks.lint", return_value=[]), \
         patch("static_checks.collect_test_samples", return_value=""), \
         patch("sys.argv", ["guardian.py"]):
        main()

    captured = capsys.readouterr()
    assert "Test Guardian Report" in captured.out
    assert "CONFIDENT" in captured.out


# Verifies: main() Phase 3 produces raw output fallback when all iterations fail to return JSON
def test_main_phase3_raw_fallback(capsys):
    phase1_resp = json.dumps({"session_id": "s1", "result": "Wrote tests."})
    phase2_resp = json.dumps({
        "session_id": "s1",
        "result": '```json\n{"complete": true, "summary": "done"}\n```',
    })
    # All Phase 3 responses: no JSON
    phase3_no_json = json.dumps({
        "session_id": "s1",
        "result": "I think everything looks fine but I cannot format JSON.",
    })

    call_count = {"n": 0}
    ordered = [phase1_resp, phase2_resp, phase3_no_json]

    def mock_run(cmd, **kwargs):
        if cmd[0] == "git":
            return MagicMock(stdout="", stderr="", returncode=0)
        resp = ordered[min(call_count["n"], len(ordered) - 1)]
        call_count["n"] += 1
        return MagicMock(stdout=resp, stderr="", returncode=0)

    with patch("subprocess.run", side_effect=mock_run), \
         patch("guardian.get_diff", return_value="+ code"), \
         patch("static_checks.run", return_value=[]), \
         patch("static_checks.lint", return_value=[]), \
         patch("static_checks.collect_test_samples", return_value=""), \
         patch("sys.argv", ["guardian.py", "--max-iter", "1"]):
        main()

    captured = capsys.readouterr()
    assert "Test Guardian Report" in captured.out
    # Should contain the raw response text in the report
    assert "cannot format JSON" in captured.out


# Verifies: main() with --all skips static_checks.run (no diff-based checks) but runs full pipeline
def test_main_all_mode_skips_static_run(capsys):
    phase1_resp = json.dumps({"session_id": "s1", "result": "Reviewed all tests."})
    phase2_resp = json.dumps({
        "session_id": "s1",
        "result": '```json\n{"complete": true, "summary": "done"}\n```',
    })
    phase3_resp = json.dumps({
        "session_id": "s1",
        "result": '```json\n{"confident": true}\n```',
    })

    call_count = {"n": 0}
    ordered = [phase1_resp, phase2_resp, phase3_resp]

    def mock_run_cmd(cmd, **kwargs):
        if cmd[0] == "git":
            return MagicMock(stdout="tests/foo.test.ts\nsrc/foo.ts\n", stderr="", returncode=0)
        resp = ordered[min(call_count["n"], len(ordered) - 1)]
        call_count["n"] += 1
        return MagicMock(stdout=resp, stderr="", returncode=0)

    static_run_called = {"called": False}
    original_static_run = static_checks.run

    def mock_static_run(diff_text):
        static_run_called["called"] = True
        return []

    with patch("subprocess.run", side_effect=mock_run_cmd), \
         patch("static_checks.run", side_effect=mock_static_run), \
         patch("static_checks.lint", return_value=[]), \
         patch("static_checks.collect_test_samples", return_value=""), \
         patch("sys.argv", ["guardian.py", "--all"]):
        main()

    captured = capsys.readouterr()
    assert "Test Guardian Report" in captured.out
    assert "**Scope**: all" in captured.out
    # static_checks.run should NOT be called in --all mode
    assert not static_run_called["called"]


# Verifies: main() Phase 3 handles confident:false with gaps — records gaps and does not set final_confident
def test_main_phase3_gaps_not_confident(capsys):
    phase1_resp = json.dumps({"session_id": "s1", "result": "Wrote tests."})
    phase2_resp = json.dumps({
        "session_id": "s1",
        "result": '```json\n{"complete": true, "summary": "done"}\n```',
    })
    phase3_resp = json.dumps({
        "session_id": "s1",
        "result": '```json\n{"confident": false, "gaps": ["missing error path test"]}\n```',
    })

    call_count = {"n": 0}
    ordered = [phase1_resp, phase2_resp, phase3_resp]

    def mock_run(cmd, **kwargs):
        if cmd[0] == "git":
            return MagicMock(stdout="", stderr="", returncode=0)
        resp = ordered[min(call_count["n"], len(ordered) - 1)]
        call_count["n"] += 1
        return MagicMock(stdout=resp, stderr="", returncode=0)

    with patch("subprocess.run", side_effect=mock_run), \
         patch("guardian.get_diff", return_value="+ code"), \
         patch("static_checks.run", return_value=[]), \
         patch("static_checks.lint", return_value=[]), \
         patch("static_checks.collect_test_samples", return_value=""), \
         patch("sys.argv", ["guardian.py", "--max-iter", "1"]):
        main()

    captured = capsys.readouterr()
    assert "Test Guardian Report" in captured.out
    assert "Gaps Identified" in captured.out
    assert "missing error path test" in captured.out
    # Should NOT show CONFIDENT
    assert "### Phase 3: CONFIDENT" not in captured.out
