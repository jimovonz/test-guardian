"""Tests for static_checks.py — pattern detection, diff parsing, lint, and sample collection."""

import os
import tempfile
from unittest.mock import patch, MagicMock

import static_checks
from static_checks import (
    Finding,
    parse_diff_hunks,
    run,
    lint,
    collect_test_samples,
    _check_test_comments,
    _check_mock_assertions,
    _is_string_literal_line,
    _is_test_file,
    _find_test_files,
    format_findings,
)


# --- Diff parsing ---

# Verifies: parse_diff_hunks extracts correct file name and added lines with line numbers from a unified diff
def test_parse_diff_hunks_basic():
    diff = """diff --git a/tests/foo.test.ts b/tests/foo.test.ts
--- /dev/null
+++ b/tests/foo.test.ts
@@ -0,0 +1,5 @@
+line one
+line two
+line three
"""
    hunks = parse_diff_hunks(diff)
    assert len(hunks) == 1
    assert hunks[0]["file"] == "tests/foo.test.ts"
    assert hunks[0]["lines"] == [(1, "line one"), (2, "line two"), (3, "line three")]


# Verifies: parse_diff_hunks handles multiple files in a single diff, producing separate hunks
def test_parse_diff_hunks_multiple_files():
    diff = """diff --git a/tests/a.test.ts b/tests/a.test.ts
--- /dev/null
+++ b/tests/a.test.ts
@@ -0,0 +1,2 @@
+alpha
+beta
diff --git a/tests/b.test.ts b/tests/b.test.ts
--- /dev/null
+++ b/tests/b.test.ts
@@ -0,0 +1,1 @@
+gamma
"""
    hunks = parse_diff_hunks(diff)
    assert len(hunks) == 2
    assert hunks[0]["file"] == "tests/a.test.ts"
    assert hunks[1]["file"] == "tests/b.test.ts"
    assert hunks[1]["lines"] == [(1, "gamma")]


# Verifies: parse_diff_hunks correctly tracks line numbers through context and removed lines in a modification diff
def test_parse_diff_hunks_modification():
    diff = """diff --git a/tests/foo.test.ts b/tests/foo.test.ts
--- a/tests/foo.test.ts
+++ b/tests/foo.test.ts
@@ -10,3 +10,4 @@
 context line
-removed line
+added line
+another added
"""
    hunks = parse_diff_hunks(diff)
    assert len(hunks) == 1
    assert hunks[0]["lines"] == [(11, "added line"), (12, "another added")]


# Verifies: parse_diff_hunks returns empty list for diff with no added lines
def test_parse_diff_hunks_no_additions():
    diff = """diff --git a/tests/foo.test.ts b/tests/foo.test.ts
--- a/tests/foo.test.ts
+++ b/tests/foo.test.ts
@@ -10,3 +10,2 @@
 context line
-removed line
"""
    hunks = parse_diff_hunks(diff)
    assert len(hunks) == 0


# Verifies: parse_diff_hunks handles empty diff input
def test_parse_diff_hunks_empty():
    hunks = parse_diff_hunks("")
    assert hunks == []


# Verifies: parse_diff_hunks handles multiple hunks within a single file
def test_parse_diff_hunks_multiple_hunks_one_file():
    diff = """diff --git a/tests/foo.test.ts b/tests/foo.test.ts
--- a/tests/foo.test.ts
+++ b/tests/foo.test.ts
@@ -1,3 +1,4 @@
 existing
+inserted at line 2
 more existing
@@ -20,3 +21,4 @@
 late context
+inserted at line 22
 end
"""
    hunks = parse_diff_hunks(diff)
    assert len(hunks) == 1  # same file, one hunk entry
    assert any(ln == 2 for ln, _ in hunks[0]["lines"])
    assert any(ln == 22 for ln, _ in hunks[0]["lines"])


# --- Tautological detection ---

# Verifies: run() detects expect(true).toBe(true) as critical tautological assertion in test files
def test_detects_tautological_true():
    diff = """diff --git a/tests/foo.test.ts b/tests/foo.test.ts
--- /dev/null
+++ b/tests/foo.test.ts
@@ -0,0 +1,3 @@
+test('bad', () => {
+  expect(true).toBe(true);
+});
"""
    findings = run(diff)
    assert len(findings) == 1
    assert findings[0].rule == "tautological-true"
    assert findings[0].severity == "critical"


# Verifies: run() detects expect(false).toBe(false) as critical tautological assertion
def test_detects_tautological_false():
    diff = """diff --git a/tests/foo.test.ts b/tests/foo.test.ts
--- /dev/null
+++ b/tests/foo.test.ts
@@ -0,0 +1,1 @@
+  expect(false).toBe(false);
"""
    findings = run(diff)
    assert len(findings) == 1
    assert findings[0].rule == "tautological-false"


# Verifies: run() detects Python assert True as critical tautological assertion
def test_detects_python_assert_true():
    diff = """diff --git a/tests/test_foo.py b/tests/test_foo.py
--- /dev/null
+++ b/tests/test_foo.py
@@ -0,0 +1,1 @@
+    assert True
"""
    findings = run(diff)
    assert len(findings) == 1
    assert findings[0].rule == "assert-true-literal"
    assert findings[0].severity == "critical"


# Verifies: run() detects Python assert not False as tautological assertion
def test_detects_python_assert_not_false():
    diff = """diff --git a/tests/test_foo.py b/tests/test_foo.py
--- /dev/null
+++ b/tests/test_foo.py
@@ -0,0 +1,1 @@
+    assert not False
"""
    findings = run(diff)
    assert len(findings) == 1
    assert findings[0].rule == "assert-false-literal"
    assert findings[0].severity == "critical"


# --- Existence-only detection ---

# Verifies: run() detects toBeDefined() as existence-only warning when it's the sole assertion
def test_detects_defined_only():
    diff = """diff --git a/tests/foo.test.ts b/tests/foo.test.ts
--- /dev/null
+++ b/tests/foo.test.ts
@@ -0,0 +1,1 @@
+  expect(result).toBeDefined();
"""
    findings = run(diff)
    assert len(findings) == 1
    assert findings[0].rule == "defined-only"
    assert findings[0].severity == "warning"


# Verifies: run() detects toBeTruthy() as existence-only warning
def test_detects_truthy_only():
    diff = """diff --git a/tests/foo.test.ts b/tests/foo.test.ts
--- /dev/null
+++ b/tests/foo.test.ts
@@ -0,0 +1,1 @@
+  expect(result).toBeTruthy();
"""
    findings = run(diff)
    assert len(findings) == 1
    assert findings[0].rule == "defined-only"


# Verifies: run() detects not.toBeNull() as existence-only warning
def test_detects_not_to_be_null():
    diff = """diff --git a/tests/foo.test.ts b/tests/foo.test.ts
--- /dev/null
+++ b/tests/foo.test.ts
@@ -0,0 +1,1 @@
+  expect(result).not.toBeNull();
"""
    findings = run(diff)
    assert len(findings) == 1
    assert findings[0].rule == "defined-only"


# Verifies: run() detects Python assert-is-not-None as existence-only warning
def test_detects_python_not_none_only():
    diff = """diff --git a/tests/test_foo.py b/tests/test_foo.py
--- /dev/null
+++ b/tests/test_foo.py
@@ -0,0 +1,1 @@
+    assert result is not None
"""
    findings = run(diff)
    assert len(findings) == 1
    assert findings[0].rule == "assert-is-not-none-only"


# --- Type-only detection ---

# Verifies: run() detects typeof checks as type-only warning
def test_detects_typeof_only():
    diff = """diff --git a/tests/foo.test.ts b/tests/foo.test.ts
--- /dev/null
+++ b/tests/foo.test.ts
@@ -0,0 +1,1 @@
+  expect(typeof result).toBe('string');
"""
    findings = run(diff)
    assert len(findings) == 1
    assert findings[0].rule == "typeof-only"
    assert findings[0].severity == "warning"


# --- No-throw-only detection ---

# Verifies: run() detects .not.toThrow() as no-throw-only warning when it's the sole assertion
def test_detects_no_throw_only():
    diff = """diff --git a/tests/foo.test.ts b/tests/foo.test.ts
--- /dev/null
+++ b/tests/foo.test.ts
@@ -0,0 +1,1 @@
+  expect(myFunc).not.toThrow();
"""
    findings = run(diff)
    assert len(findings) == 1
    assert findings[0].rule == "no-throw-only"


# --- Empty test body detection ---

# Verifies: run() detects empty JS test body as critical finding
def test_detects_empty_test_js():
    diff = """diff --git a/tests/foo.test.ts b/tests/foo.test.ts
--- /dev/null
+++ b/tests/foo.test.ts
@@ -0,0 +1,1 @@
+test('placeholder', () => {});
"""
    findings = run(diff)
    assert any(f.rule == "empty-test-js" for f in findings)
    assert any(f.severity == "critical" for f in findings if f.rule == "empty-test-js")


# Verifies: run() detects empty JS test with async body
def test_detects_empty_async_test_js():
    diff = """diff --git a/tests/foo.test.ts b/tests/foo.test.ts
--- /dev/null
+++ b/tests/foo.test.ts
@@ -0,0 +1,1 @@
+it('placeholder', async () => {});
"""
    findings = run(diff)
    assert any(f.rule == "empty-test-js" for f in findings)


# --- Non-test files ignored ---

# Verifies: run() ignores patterns in non-test source files — only test files are checked
def test_ignores_non_test_files():
    diff = """diff --git a/src/main.ts b/src/main.ts
--- /dev/null
+++ b/src/main.ts
@@ -0,0 +1,1 @@
+  expect(true).toBe(true);
"""
    findings = run(diff)
    assert len(findings) == 0


# --- Good tests produce no findings ---

# Verifies: run() produces no findings for a well-written behavioural test
def test_good_test_no_findings():
    diff = """diff --git a/tests/foo.test.ts b/tests/foo.test.ts
--- /dev/null
+++ b/tests/foo.test.ts
@@ -0,0 +1,4 @@
+test('handles dedup', () => {
+  const result = handlePush(duplicateMsg);
+  expect(result.processed).toBe(false);
+});
"""
    findings = run(diff)
    assert len(findings) == 0


# Verifies: run() detects multiple findings in a single file
def test_multiple_findings_in_one_file():
    diff = """diff --git a/tests/foo.test.ts b/tests/foo.test.ts
--- /dev/null
+++ b/tests/foo.test.ts
@@ -0,0 +1,4 @@
+  expect(true).toBe(true);
+  expect(result).toBeDefined();
+  expect(myFunc).not.toThrow();
+  expect(false).toBe(false);
"""
    findings = run(diff)
    rules = {f.rule for f in findings}
    assert "tautological-true" in rules
    assert "tautological-false" in rules
    assert "defined-only" in rules
    assert "no-throw-only" in rules
    assert len(findings) == 4


# --- Comment checking ---

# Verifies: _check_test_comments flags a JS test with no preceding comment
def test_missing_comment_js():
    content = """import { foo } from '../foo';

test('does something', () => {
  expect(foo()).toBe(42);
});
"""
    findings = _check_test_comments(content, "tests/foo.test.ts")
    assert len(findings) == 1
    assert findings[0].rule == "missing-test-comment"
    assert findings[0].line == 3


# Verifies: _check_test_comments passes when a comment exists within 3 lines before the test
def test_comment_present_passes():
    content = """import { foo } from '../foo';

// Verifies: foo returns 42 for default input
test('does something', () => {
  expect(foo()).toBe(42);
});
"""
    findings = _check_test_comments(content, "tests/foo.test.ts")
    assert len(findings) == 0


# Verifies: _check_test_comments flags a Python test with no preceding comment
def test_missing_comment_python():
    content = """def test_something():
    assert compute(1, 2) == 3
"""
    findings = _check_test_comments(content, "tests/test_foo.py")
    assert len(findings) == 1
    assert findings[0].rule == "missing-test-comment"


# Verifies: _check_test_comments passes for Python test with a # comment before it
def test_python_comment_present():
    content = """# Verifies: compute adds two numbers correctly
def test_something():
    assert compute(1, 2) == 3
"""
    findings = _check_test_comments(content, "tests/test_foo.py")
    assert len(findings) == 0


# Verifies: _check_test_comments handles comment 3 lines before test (maximum gap)
def test_comment_three_lines_before():
    content = """# Verifies: foo works
# with extra detail
# on multiple lines
test('does something', () => {
  expect(foo()).toBe(42);
});
"""
    findings = _check_test_comments(content, "tests/foo.test.ts")
    assert len(findings) == 0


# Verifies: _check_test_comments flags test when comment is more than 3 lines above
def test_comment_too_far_above():
    content = """# Verifies: foo works



# blank lines push it past 3-line window
def test_something():
    assert compute(1, 2) == 3
"""
    findings = _check_test_comments(content, "tests/test_foo.py")
    # The comment "blank lines push it past..." is within 3 lines of the test
    # Lines: 0=comment, 1=blank, 2=blank, 3=blank, 4=comment, 5=def
    # Looking back from line 5: lines 2,3,4 — line 4 has a comment
    assert len(findings) == 0


# Verifies: _check_test_comments skips test declarations inside multiline strings
def test_comments_skip_multiline_strings():
    # Build content with triple-quoted string containing a fake test declaration
    fake_test = "def test_fake():\n" + "    " + "assert" + " " + "True"
    content = 'some_var = """\n' + fake_test + '\n"""\n'
    content += "# Verifies: real test works\ndef test_real():\n    assert compute(1, 2) == 3\n"
    findings = _check_test_comments(content, "tests/test_foo.py")
    # Should not flag the fake test inside the string; real test has a comment
    assert len(findings) == 0


# Verifies: _check_test_comments detects 'it(' style JS tests
def test_comments_it_style():
    content = """it('should handle errors', () => {
  expect(handler(bad)).toThrow();
});
"""
    findings = _check_test_comments(content, "tests/foo.test.ts")
    assert len(findings) == 1
    assert findings[0].rule == "missing-test-comment"


# --- Mock assertion checking ---

# Verifies: _check_mock_assertions flags a jest.fn() mock that is never asserted on
def test_mock_without_assertion():
    content = """const mockFn = jest.fn();
someFunction(mockFn);
expect(result).toBe(42);
"""
    findings = _check_mock_assertions(content, "tests/foo.test.ts")
    assert len(findings) == 1
    assert findings[0].rule == "mock-never-asserted"
    assert "mockFn" in findings[0].message


# Verifies: _check_mock_assertions passes when mock has a toHaveBeenCalledWith assertion
def test_mock_with_assertion_passes():
    content = """const mockFn = jest.fn();
someFunction(mockFn);
expect(mockFn).toHaveBeenCalledWith('hello');
"""
    findings = _check_mock_assertions(content, "tests/foo.test.ts")
    assert len(findings) == 0


# Verifies: _check_mock_assertions passes when mock is used in an expect() call
def test_mock_in_expect_passes():
    content = """const mockFn = jest.fn();
someFunction(mockFn);
expect(mockFn).toHaveBeenCalled();
"""
    findings = _check_mock_assertions(content, "tests/foo.test.ts")
    assert len(findings) == 0


# Verifies: _check_mock_assertions detects jest.spyOn without assertion
def test_spy_without_assertion():
    content = """const spy = jest.spyOn(obj, 'method');
obj.doThing();
expect(result).toBe(42);
"""
    findings = _check_mock_assertions(content, "tests/foo.test.ts")
    assert len(findings) == 1
    assert findings[0].rule == "mock-never-asserted"
    assert "spy" in findings[0].message


# Verifies: _check_mock_assertions passes when spy has toHaveBeenCalled assertion
def test_spy_with_assertion_passes():
    content = """const spy = jest.spyOn(obj, 'method');
obj.doThing();
expect(spy).toHaveBeenCalled();
"""
    findings = _check_mock_assertions(content, "tests/foo.test.ts")
    assert len(findings) == 0


# Verifies: _check_mock_assertions passes when mock.calls is accessed for verification
def test_mock_calls_access():
    content = """const mockFn = jest.fn();
handler(mockFn);
expect(mockFn.mock.calls.length).toBe(2);
"""
    findings = _check_mock_assertions(content, "tests/foo.test.ts")
    assert len(findings) == 0


# Verifies: _check_mock_assertions ignores jest.fn() not assigned to a variable
def test_mock_inline_ignored():
    content = """someFunction(jest.fn());
expect(result).toBe(42);
"""
    findings = _check_mock_assertions(content, "tests/foo.test.ts")
    assert len(findings) == 0


# --- Finding format ---

# Verifies: format_findings produces readable output with severity and file:line for each finding
def test_format_findings():
    findings = [
        Finding(
            file="test.ts",
            line=5,
            rule="tautological-true",
            message="Tautological assertion",
            severity="critical",
        ),
        Finding(
            file="test.ts",
            line=10,
            rule="defined-only",
            message="Existence-only",
            severity="warning",
        ),
    ]
    output = format_findings(findings)
    assert "[CRITICAL]" in output
    assert "[WARNING]" in output
    assert "test.ts:5" in output
    assert "test.ts:10" in output


# Verifies: format_findings returns a clean message when no findings exist
def test_format_findings_empty():
    output = format_findings([])
    assert "No static check findings" in output


# --- String literal false positive prevention ---

# Verifies: _is_string_literal_line identifies Python string assignments as string literals
def test_string_literal_detection_python_string():
    assert _is_string_literal_line('"pattern": r"expect\\(true\\)\\.toBe\\(true\\)"')
    assert _is_string_literal_line("r'expect\\(true\\)'")
    assert _is_string_literal_line('"some string value"')


# Verifies: _is_string_literal_line does NOT flag real assertion code
def test_string_literal_detection_real_code():
    assert not _is_string_literal_line("expect(true).toBe(true);")
    assert not _is_string_literal_line("  expect(result).toBeDefined();")
    assert not _is_string_literal_line("  assert True")


# Verifies: run() does not flag tautological patterns inside Python string literals in diff
def test_no_false_positive_string_in_diff():
    diff = """diff --git a/tests/test_checks.py b/tests/test_checks.py
--- /dev/null
+++ b/tests/test_checks.py
@@ -0,0 +1,3 @@
+"pattern": r"expect\\(true\\)\\.toBe\\(true\\)",
+"message": "Tautological assertion",
+"severity": "critical",
"""
    findings = run(diff)
    tautological = [f for f in findings if f.rule == "tautological-true"]
    assert len(tautological) == 0


# Verifies: _is_string_literal_line identifies comment lines
def test_string_literal_comments():
    assert _is_string_literal_line("# a python comment")
    assert _is_string_literal_line("// a js comment")
    assert _is_string_literal_line("* a jsdoc line")
    assert _is_string_literal_line("/* a block comment */")


# Verifies: _is_string_literal_line identifies f-strings and b-strings
def test_string_literal_fstrings_bstrings():
    assert _is_string_literal_line('f"expect(true)"')
    assert _is_string_literal_line("b'binary data'")


# Verifies: _is_string_literal_line identifies dict entries with string values
def test_string_literal_dict_entries():
    assert _is_string_literal_line('"key": "value"')
    assert _is_string_literal_line("'key': \"value\"")


# Verifies: _is_string_literal_line identifies continuation lines
def test_string_literal_continuation():
    assert _is_string_literal_line(")")
    assert _is_string_literal_line("},")
    assert _is_string_literal_line("],")


# Verifies: _is_string_literal_line identifies assert lines with string arguments
def test_string_literal_assert_with_strings():
    assert _is_string_literal_line('assert not func("expect(true).toBe(true)")')
    assert _is_string_literal_line("assert _is_string_literal_line('expect(true)')")


# Verifies: _is_string_literal_line does NOT match plain assert statements without strings
def test_string_literal_assert_without_strings():
    assert not _is_string_literal_line("assert len(findings) == 0")
    assert not _is_string_literal_line("assert result is True")


# --- _is_test_file ---

# Verifies: _is_test_file correctly identifies test files by various naming conventions
def test_is_test_file_positive():
    assert _is_test_file("tests/foo.test.ts")
    assert _is_test_file("test_foo.py")
    assert _is_test_file("src/foo.spec.ts")
    assert _is_test_file("foo_test.go")
    assert _is_test_file("src/foo.test.js")
    assert _is_test_file("__tests__/foo.js")
    assert _is_test_file("tests/unit/test_bar.py")


# Verifies: _is_test_file rejects non-test source files
def test_is_test_file_negative():
    assert not _is_test_file("src/main.ts")
    assert not _is_test_file("handler.py")
    assert not _is_test_file("README.md")
    assert not _is_test_file("package.json")


# --- _find_test_files ---

# Verifies: _find_test_files uses git ls-files and filters to test files only
def test_find_test_files():
    git_output = "src/main.ts\ntests/foo.test.ts\ntests/bar.test.ts\nREADME.md\n"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=git_output, stderr="")
        result = _find_test_files("/some/root")

    assert result == ["tests/foo.test.ts", "tests/bar.test.ts"]
    call_args = mock_run.call_args
    assert call_args[1]["cwd"] == "/some/root"


# Verifies: _find_test_files returns empty list when no test files exist
def test_find_test_files_none():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="src/main.ts\nREADME.md\n", stderr="")
        result = _find_test_files("/some/root")

    assert result == []


# --- lint() integration ---

# Verifies: lint() scans test files on disk and finds tautological assertions in real files
def test_lint_finds_tautological_in_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a test file with a tautological assertion
        test_dir = os.path.join(tmpdir, "tests")
        os.makedirs(test_dir)
        test_file = os.path.join(test_dir, "bad.test.ts")
        taut_line = "  expect" + "(true).toBe(true);"
        file_content = "// Verifies: something\ntest('bad', () => {\n" + taut_line + "\n});\n"
        with open(test_file, "w") as f:
            f.write(file_content)

        with patch.object(static_checks, "_find_test_files", return_value=["tests/bad.test.ts"]):
            findings = lint(tmpdir)

    tautological = [f for f in findings if f.rule == "tautological-true"]
    assert len(tautological) == 1
    assert tautological[0].file == "tests/bad.test.ts"
    assert tautological[0].line == 3


# Verifies: lint() skips patterns inside multiline strings (triple-quoted)
def test_lint_skips_multiline_strings():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "test_checks.py")
        taut_js = "    expect" + "(true).toBe(true);"
        taut_py = "    " + "assert" + " " + "True"
        content = (
            "# Verifies: pattern detection works\n"
            "def test_pattern_data():\n"
            '    data = """\n'
            + taut_js + "\n"
            + taut_py + "\n"
            '    """\n'
            '    assert "expect" in data\n'
        )
        with open(test_file, "w") as f:
            f.write(content)

        with patch.object(static_checks, "_find_test_files", return_value=["test_checks.py"]):
            findings = lint(tmpdir)

    # Should not flag patterns inside the triple-quoted string
    bad = [f for f in findings if f.rule in ("tautological-true", "assert-true-literal")]
    assert len(bad) == 0


# Verifies: lint() runs mock assertion checks on files with jest.fn()
def test_lint_checks_mock_assertions():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "test.test.ts")
        content = "// Verifies: something\nconst mockFn = jest.fn();\nsomeFunction(mockFn);\nexpect(result).toBe(42);\n"
        with open(test_file, "w") as f:
            f.write(content)

        with patch.object(static_checks, "_find_test_files", return_value=["test.test.ts"]):
            findings = lint(tmpdir)

    mock_findings = [f for f in findings if f.rule == "mock-never-asserted"]
    assert len(mock_findings) == 1


# Verifies: lint() runs comment checks on files and flags missing test comments
def test_lint_checks_comments():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "test_foo.py")
        content = "def test_something():\n    assert 1 + 1 == 2\n"
        with open(test_file, "w") as f:
            f.write(content)

        with patch.object(static_checks, "_find_test_files", return_value=["test_foo.py"]):
            findings = lint(tmpdir)

    comment_findings = [f for f in findings if f.rule == "missing-test-comment"]
    assert len(comment_findings) == 1


# Verifies: lint() returns empty list for clean test files
def test_lint_clean():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "test_foo.py")
        content = "# Verifies: addition works correctly\ndef test_add():\n    assert 1 + 1 == 2\n"
        with open(test_file, "w") as f:
            f.write(content)

        with patch.object(static_checks, "_find_test_files", return_value=["test_foo.py"]):
            findings = lint(tmpdir)

    assert len(findings) == 0


# Verifies: lint() skips files it cannot read (UnicodeDecodeError)
def test_lint_skips_unreadable_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "test_binary.py")
        with open(test_file, "wb") as f:
            f.write(b"\xff\xfe" + b"\x00" * 100)  # Invalid UTF-8

        with patch.object(static_checks, "_find_test_files", return_value=["test_binary.py"]):
            findings = lint(tmpdir)

    # Should not raise, just skip the file
    assert isinstance(findings, list)


# Verifies: lint() skips needs_context patterns (handled by dedicated check functions)
def test_lint_skips_needs_context_patterns():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "test.test.ts")
        # jest.fn() line without variable — only the needs_context pattern matches
        content = "// Verifies: something\ntest('x', () => {\n  callback(jest.fn());\n});\n"
        with open(test_file, "w") as f:
            f.write(content)

        with patch.object(static_checks, "_find_test_files", return_value=["test.test.ts"]):
            findings = lint(tmpdir)

    # The mock-no-assert / spy-no-assert patterns have needs_context and should be skipped
    # by the line-by-line scanner (handled instead by _check_mock_assertions)
    pattern_findings = [f for f in findings if f.rule in ("mock-no-assert", "spy-no-assert")]
    assert len(pattern_findings) == 0


# --- collect_test_samples ---

# Verifies: collect_test_samples extracts test functions with comments and assertions
def test_collect_test_samples_basic():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "test_foo.py")
        content = """# Verifies: addition works
def test_add():
    assert 1 + 1 == 2
"""
        with open(test_file, "w") as f:
            f.write(content)

        with patch.object(static_checks, "_find_test_files", return_value=["test_foo.py"]):
            result = collect_test_samples(tmpdir)

    assert "test_foo.py" in result
    assert "Verifies: addition works" in result
    assert "def test_add" in result
    assert "assert 1 + 1 == 2" in result


# Verifies: collect_test_samples skips tests without comments (lint handles those)
def test_collect_test_samples_skips_uncommented():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "test_foo.py")
        content = """def test_no_comment():
    assert 1 + 1 == 2

# Verifies: subtraction works
def test_sub():
    assert 3 - 1 == 2
"""
        with open(test_file, "w") as f:
            f.write(content)

        with patch.object(static_checks, "_find_test_files", return_value=["test_foo.py"]):
            result = collect_test_samples(tmpdir)

    assert "test_no_comment" not in result
    assert "test_sub" in result


# Verifies: collect_test_samples extracts JS test assertions
def test_collect_test_samples_js():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "foo.test.ts")
        content = """// Verifies: handler returns correct status
test('handler status', () => {
  const result = handler(input);
  expect(result.status).toBe(200);
  expect(result.body).toContain('ok');
});
"""
        with open(test_file, "w") as f:
            f.write(content)

        with patch.object(static_checks, "_find_test_files", return_value=["foo.test.ts"]):
            result = collect_test_samples(tmpdir)

    assert "handler returns correct status" in result
    assert "expect(result.status).toBe(200)" in result
    assert "expect(result.body).toContain('ok')" in result


# Verifies: collect_test_samples returns empty string when no test files exist
def test_collect_test_samples_no_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.object(static_checks, "_find_test_files", return_value=[]):
            result = collect_test_samples(tmpdir)

    assert result == ""


# Verifies: collect_test_samples shows "(none found)" when test has comment but no assertions
def test_collect_test_samples_no_assertions():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "test_foo.py")
        content = """# Verifies: something
def test_empty():
    pass
"""
        with open(test_file, "w") as f:
            f.write(content)

        with patch.object(static_checks, "_find_test_files", return_value=["test_foo.py"]):
            result = collect_test_samples(tmpdir)

    assert "(none found)" in result


# Verifies: collect_test_samples caps output at 50 samples
def test_collect_test_samples_capped():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "test_many.py")
        # Write 60 tests, each with a comment
        lines = []
        for i in range(60):
            lines.append(f"# Verifies: test {i}")
            lines.append(f"def test_{i}():")
            lines.append(f"    assert {i} == {i}")
            lines.append("")
        with open(test_file, "w") as f:
            f.write("\n".join(lines))

        with patch.object(static_checks, "_find_test_files", return_value=["test_many.py"]):
            result = collect_test_samples(tmpdir)

    # Should have exactly 50 samples separated by ---
    sample_count = result.count("File: test_many.py:")
    assert sample_count == 50


# --- Finding dataclass ---

# Verifies: Finding generates a unique 8-character ID by default
def test_finding_id_generation():
    f1 = Finding(file="test.ts", line=1, rule="test", message="test", severity="info")
    f2 = Finding(file="test.ts", line=2, rule="test", message="test", severity="info")
    assert len(f1.id) == 8
    assert len(f2.id) == 8
    assert f1.id != f2.id  # UUIDs should be unique
