"""Tests for static_checks.py — pattern detection and diff parsing."""

import static_checks
from static_checks import Finding, parse_diff_hunks, run, lint, _check_test_comments, _check_mock_assertions


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


# --- Finding format ---

# Verifies: format_findings produces readable output with severity and file:line for each finding
def test_format_findings():
    findings = [
        Finding(file="test.ts", line=5, rule="tautological-true",
                message="Tautological assertion", severity="critical"),
        Finding(file="test.ts", line=10, rule="defined-only",
                message="Existence-only", severity="warning"),
    ]
    output = static_checks.format_findings(findings)
    assert "[CRITICAL]" in output
    assert "[WARNING]" in output
    assert "test.ts:5" in output
    assert "test.ts:10" in output


# Verifies: format_findings returns a clean message when no findings exist
def test_format_findings_empty():
    output = static_checks.format_findings([])
    assert "No static check findings" in output
