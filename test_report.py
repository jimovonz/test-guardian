"""Tests for report.py — format_report output verification."""

from static_checks import Finding
from report import format_report


# --- Basic report structure ---

# Verifies: format_report produces a report with the correct heading and scope
def test_report_heading_and_scope():
    result = format_report(
        phases=[],
        static_findings=[],
        final_confident=True,
        final_gaps=[],
        elapsed=120.0,
        scope_mode="diff",
    )
    assert "# Test Guardian Report" in result
    assert "**Scope**: diff" in result


# Verifies: format_report shows elapsed time rounded to whole seconds
def test_report_elapsed_time():
    result = format_report(
        phases=[],
        static_findings=[],
        final_confident=True,
        final_gaps=[],
        elapsed=345.7,
        scope_mode="all",
    )
    assert "**Time**: 346s" in result
    assert "**Scope**: all" in result


# --- Phase iteration counts ---

# Verifies: format_report counts phase 2, 2.5, and 3 iterations correctly from the phases list
def test_report_iteration_counts():
    phases = [
        {"phase": 1, "name": "Write tests", "response": "done"},
        {"phase": 2, "name": "Completion check (iteration 1)", "result": {"complete": False, "remaining": ["gap"]}, "response": "..."},
        {"phase": 2, "name": "Confirm completion", "iterations": 2, "result": {"complete": True, "summary": "all done"}},
        {"phase": 2.5, "name": "Lint gate (iteration 1)", "lint_findings": 3, "response": "fixed"},
        {"phase": 2.5, "name": "Quality gate passed", "iterations": 2},
        {"phase": 3, "name": "Confidence check", "iterations": 1, "result": {"confident": True}},
    ]
    result = format_report(
        phases=phases,
        static_findings=[],
        final_confident=True,
        final_gaps=[],
        elapsed=60.0,
        scope_mode="diff",
    )
    assert "**Completion checks**: 2 iteration(s)" in result
    assert "**Quality gate checks**: 2 iteration(s)" in result
    assert "**Confidence checks**: 1 iteration(s)" in result


# --- Static findings section ---

# Verifies: format_report includes static findings with severity and file:line when findings are present
def test_report_static_findings_included():
    findings = [
        Finding(file="test.ts", line=5, rule="tautological-true",
                message="Tautological assertion", severity="critical"),
        Finding(file="test.ts", line=12, rule="defined-only",
                message="Existence-only assertion", severity="warning"),
    ]
    result = format_report(
        phases=[],
        static_findings=findings,
        final_confident=True,
        final_gaps=[],
        elapsed=10.0,
        scope_mode="diff",
    )
    assert "## Static Checks (2 findings)" in result
    assert "[CRITICAL]" in result
    assert "`test.ts:5`" in result
    assert "[WARNING]" in result
    assert "`test.ts:12`" in result
    assert "Phase 1 prompt" in result


# Verifies: format_report omits the static findings section entirely when there are no findings
def test_report_no_static_findings():
    result = format_report(
        phases=[],
        static_findings=[],
        final_confident=True,
        final_gaps=[],
        elapsed=10.0,
        scope_mode="diff",
    )
    assert "## Static Checks" not in result


# --- Phase 1 rendering ---

# Verifies: format_report renders Phase 1 with truncated response if it exceeds 500 chars
def test_report_phase1_truncated():
    long_response = "A" * 600
    phases = [{"phase": 1, "name": "Write tests", "response": long_response}]
    result = format_report(
        phases=phases,
        static_findings=[],
        final_confident=True,
        final_gaps=[],
        elapsed=10.0,
        scope_mode="diff",
    )
    assert "### Phase 1: Write Tests" in result
    assert "... (truncated)" in result
    # Should have first 500 chars but not all 600
    assert "A" * 500 in result
    assert "A" * 600 not in result


# Verifies: format_report renders Phase 1 without truncation for short responses
def test_report_phase1_short():
    phases = [{"phase": 1, "name": "Write tests", "response": "Wrote 5 tests."}]
    result = format_report(
        phases=phases,
        static_findings=[],
        final_confident=True,
        final_gaps=[],
        elapsed=10.0,
        scope_mode="diff",
    )
    assert "Wrote 5 tests." in result
    assert "(truncated)" not in result


# --- Phase 2 rendering ---

# Verifies: format_report renders Phase 2 completion with the summary text
def test_report_phase2_complete():
    phases = [
        {"phase": 2, "name": "Confirm completion", "iterations": 1,
         "result": {"complete": True, "summary": "Added tests for all handlers"}},
    ]
    result = format_report(
        phases=phases,
        static_findings=[],
        final_confident=True,
        final_gaps=[],
        elapsed=10.0,
        scope_mode="diff",
    )
    assert "### Phase 2: Completion Confirmed" in result
    assert "Added tests for all handlers" in result


# Verifies: format_report renders Phase 2 incomplete with remaining work items
def test_report_phase2_incomplete():
    phases = [
        {"phase": 2, "name": "Completion check (iteration 1)",
         "result": {"complete": False, "remaining": ["error path for handlePush", "geofence test"]},
         "response": "..."},
    ]
    result = format_report(
        phases=phases,
        static_findings=[],
        final_confident=False,
        final_gaps=[],
        elapsed=10.0,
        scope_mode="diff",
    )
    assert "Identified remaining work" in result
    assert "error path for handlePush" in result
    assert "geofence test" in result


# --- Phase 2.5 rendering ---

# Verifies: format_report renders lint gate findings with count
def test_report_phase25_lint():
    phases = [
        {"phase": 2.5, "name": "Lint gate (iteration 1)", "lint_findings": 4, "response": "fixed them"},
    ]
    result = format_report(
        phases=phases,
        static_findings=[],
        final_confident=True,
        final_gaps=[],
        elapsed=10.0,
        scope_mode="diff",
    )
    assert "### Quality Gate: Lint (4 findings)" in result
    assert "Sent 4 static check findings" in result


# Verifies: format_report renders comment validation mismatches
def test_report_phase25_comment_validation():
    phases = [
        {"phase": 2.5, "name": "Comment validation (iteration 1)",
         "result": {"mismatches": ["test.ts:42 — comment claims X but only checks Y"]},
         "response": "..."},
    ]
    result = format_report(
        phases=phases,
        static_findings=[],
        final_confident=True,
        final_gaps=[],
        elapsed=10.0,
        scope_mode="diff",
    )
    assert "### Quality Gate: Comment Validation (1 mismatches)" in result
    assert "test.ts:42" in result


# Verifies: format_report renders quality gate passed with iteration count
def test_report_phase25_passed():
    phases = [
        {"phase": 2.5, "name": "Quality gate passed", "iterations": 2},
    ]
    result = format_report(
        phases=phases,
        static_findings=[],
        final_confident=True,
        final_gaps=[],
        elapsed=10.0,
        scope_mode="diff",
    )
    assert "### Quality Gate: Passed (in 2 iteration(s))" in result


# --- Phase 3 rendering ---

# Verifies: format_report renders Phase 3 confident result
def test_report_phase3_confident():
    phases = [
        {"phase": 3, "name": "Confidence check", "iterations": 1,
         "result": {"confident": True}},
    ]
    result = format_report(
        phases=phases,
        static_findings=[],
        final_confident=True,
        final_gaps=[],
        elapsed=10.0,
        scope_mode="diff",
    )
    assert "### Phase 3: CONFIDENT" in result


# Verifies: format_report renders Phase 3 gaps when not confident
def test_report_phase3_gaps():
    phases = [
        {"phase": 3, "name": "Confidence check (iteration 1)",
         "result": {"confident": False, "gaps": ["missing dedup test", "no error path for X"]},
         "response": "..."},
    ]
    result = format_report(
        phases=phases,
        static_findings=[],
        final_confident=False,
        final_gaps=["missing dedup test", "no error path for X"],
        elapsed=10.0,
        scope_mode="diff",
    )
    assert "### Phase 3: Gaps Identified" in result
    assert "missing dedup test" in result
    assert "no error path for X" in result


# Verifies: format_report renders Phase 3 raw output fallback when no JSON was extracted
def test_report_phase3_raw_fallback():
    phases = [
        {"phase": 3, "name": "Confidence check (raw output)",
         "response": "I believe the tests are comprehensive but I'm not sure about edge cases."},
    ]
    result = format_report(
        phases=phases,
        static_findings=[],
        final_confident=False,
        final_gaps=[],
        elapsed=10.0,
        scope_mode="diff",
    )
    assert "### Phase 3: Confidence Assessment" in result
    assert "comprehensive but I'm not sure" in result


# --- Full integration ---

# Verifies: format_report produces a coherent report with all phases present in correct order
def test_report_full_integration():
    phases = [
        {"phase": 1, "name": "Write tests", "response": "Wrote tests for all handlers."},
        {"phase": 2, "name": "Confirm completion", "iterations": 1,
         "result": {"complete": True, "summary": "12 tests added"}},
        {"phase": 2.5, "name": "Quality gate passed", "iterations": 1},
        {"phase": 3, "name": "Confidence check", "iterations": 1,
         "result": {"confident": True}},
    ]
    findings = [
        Finding(file="test.ts", line=5, rule="tautological-true",
                message="Tautological", severity="critical"),
    ]
    result = format_report(
        phases=phases,
        static_findings=findings,
        final_confident=True,
        final_gaps=[],
        elapsed=240.5,
        scope_mode="diff",
    )
    # All sections present
    assert "# Test Guardian Report" in result
    assert "## Static Checks (1 findings)" in result
    assert "## Phase Summary" in result
    assert "### Phase 1: Write Tests" in result
    assert "### Phase 2: Completion Confirmed" in result
    assert "### Quality Gate: Passed" in result
    assert "### Phase 3: CONFIDENT" in result
    assert "**Time**: 240s" in result
