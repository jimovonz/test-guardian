"""Static checks for known-bad test patterns. Zero LLM cost."""

import re
import uuid
from dataclasses import dataclass, field


@dataclass
class Finding:
    file: str
    line: int
    rule: str
    message: str
    severity: str  # critical, warning, info
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])


PATTERNS = [
    # JavaScript/TypeScript tautological
    {
        "id": "tautological-true",
        "pattern": r"expect\(true\)\.toBe\(true\)",
        "message": "Tautological assertion — always passes regardless of code behaviour",
        "severity": "critical",
    },
    {
        "id": "tautological-false",
        "pattern": r"expect\(false\)\.toBe\(false\)",
        "message": "Tautological assertion — always passes regardless of code behaviour",
        "severity": "critical",
    },
    # Existence-only assertions
    {
        "id": "defined-only",
        "pattern": r"expect\([^)]+\)\.(toBeDefined|toBeTruthy|not\.toBeNull|not\.toBeUndefined)\(\)\s*;?\s*$",
        "message": "Existence-only assertion — verifies something exists but not its value or behaviour",
        "severity": "warning",
    },
    # Type-only assertions
    {
        "id": "typeof-only",
        "pattern": r"expect\(typeof\s+\w+\)\.toBe\(",
        "message": "Type-only assertion — verifies type but not behaviour",
        "severity": "warning",
    },
    # No-throw-only
    {
        "id": "no-throw-only",
        "pattern": r"expect\([^)]+\)\.not\.toThrow\(\)\s*;?\s*$",
        "message": "No-throw-only assertion — verifies function doesn't throw but not what it does",
        "severity": "warning",
    },
    # Empty test bodies (JS/TS)
    {
        "id": "empty-test-js",
        "pattern": r"(it|test)\(['\"][^'\"]+['\"],\s*(async\s*)?\(\)\s*=>\s*\{\s*\}\)",
        "message": "Empty test body — placeholder with no assertions",
        "severity": "critical",
    },
    # Python tautological
    {
        "id": "assert-true-literal",
        "pattern": r"^\s*assert\s+True\s*$",
        "message": "Tautological assertion — assert True always passes",
        "severity": "critical",
    },
    {
        "id": "assert-false-literal",
        "pattern": r"^\s*assert\s+not\s+False\s*$",
        "message": "Tautological assertion — assert not False always passes",
        "severity": "critical",
    },
    # Python existence-only
    {
        "id": "assert-is-not-none-only",
        "pattern": r"^\s*assert\s+\w+\s+is\s+not\s+None\s*$",
        "message": "Existence-only assertion — verifies not None but not the value",
        "severity": "warning",
    },
    # Python empty test
    {
        "id": "empty-test-py",
        "pattern": r"def\s+test_\w+\(.*\):\s*\n\s+pass\s*$",
        "message": "Empty test body — placeholder with no assertions",
        "severity": "critical",
    },
]

# Patterns for lint mode (run against full file content, not diff)
LINT_PATTERNS = PATTERNS + [
    # Mock without assertion (JS/TS)
    {
        "id": "mock-no-assert",
        "pattern": r"jest\.fn\(\)",
        "message": "Mock created — verify it has a corresponding toHaveBeenCalled/toHaveBeenCalledWith assertion",
        "severity": "info",
        "needs_context": True,
    },
    {
        "id": "spy-no-assert",
        "pattern": r"jest\.spyOn\(",
        "message": "Spy created — verify it has a corresponding toHaveBeenCalled/toHaveBeenCalledWith assertion",
        "severity": "info",
        "needs_context": True,
    },
]


def parse_diff_hunks(diff_text: str) -> list[dict]:
    """Parse a unified diff into per-file hunks with added lines."""
    hunks = []
    current_file = None
    current_lines = []
    line_num = 0

    for raw_line in diff_text.splitlines():
        if raw_line.startswith("diff --git"):
            if current_file and current_lines:
                hunks.append({"file": current_file, "lines": current_lines})
            current_file = None
            current_lines = []
            line_num = 0
        elif raw_line.startswith("+++ b/"):
            current_file = raw_line[6:]
        elif raw_line.startswith("@@ "):
            # Parse line number from hunk header
            match = re.search(r"\+(\d+)", raw_line)
            if match:
                line_num = int(match.group(1)) - 1
        elif raw_line.startswith("+") and not raw_line.startswith("+++"):
            line_num += 1
            current_lines.append((line_num, raw_line[1:]))
        elif raw_line.startswith("-"):
            pass  # removed lines don't affect line numbering
        else:
            line_num += 1

    if current_file and current_lines:
        hunks.append({"file": current_file, "lines": current_lines})

    return hunks


def run(diff_text: str) -> list[Finding]:
    """Run static checks against added lines in a diff."""
    findings = []
    hunks = parse_diff_hunks(diff_text)

    for hunk in hunks:
        # Only check test files
        fname = hunk["file"]
        is_test = any(
            p in fname
            for p in ["test", "spec", "_test.", ".test.", "tests/", "__tests__/"]
        )
        if not is_test:
            continue

        for line_num, line_content in hunk["lines"]:
            for pattern_def in PATTERNS:
                if re.search(pattern_def["pattern"], line_content):
                    findings.append(
                        Finding(
                            file=fname,
                            line=line_num,
                            rule=pattern_def["id"],
                            message=pattern_def["message"],
                            severity=pattern_def["severity"],
                        )
                    )

    return findings


def _is_test_file(path: str) -> bool:
    """Check if a file path looks like a test file."""
    return any(
        p in path
        for p in ["test", "spec", "_test.", ".test.", "tests/", "__tests__/"]
    )


def _find_test_files(root: str) -> list[str]:
    """Find all test files under root using git ls-files."""
    import subprocess

    result = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, cwd=root
    )
    return [f for f in result.stdout.strip().splitlines() if _is_test_file(f)]


def _check_mock_assertions(content: str, file: str) -> list[Finding]:
    """Check that mocks/spies have corresponding assertions."""
    findings = []
    lines = content.splitlines()

    for i, line in enumerate(lines, 1):
        # Check for jest.fn() or jest.spyOn(
        if re.search(r"jest\.fn\(\)|jest\.spyOn\(", line):
            # Extract variable name
            var_match = re.match(r"\s*(?:const|let|var)\s+(\w+)", line)
            if var_match:
                var_name = var_match.group(1)
                # Look for assertion on this mock anywhere in the file
                has_assert = any(
                    re.search(
                        rf"{re.escape(var_name)}\.(toHaveBeenCalled|toHaveBeenCalledWith|mock\.calls|mock\.results)",
                        l,
                    )
                    or re.search(
                        rf"expect\({re.escape(var_name)}\)", l
                    )
                    for l in lines
                )
                if not has_assert:
                    findings.append(
                        Finding(
                            file=file,
                            line=i,
                            rule="mock-never-asserted",
                            message=f"Mock `{var_name}` created but never asserted on — mock has no verification",
                            severity="warning",
                        )
                    )

    return findings


def _check_test_comments(content: str, file: str) -> list[Finding]:
    """Check that each test has a preceding comment justifying its efficacy."""
    findings = []
    lines = content.splitlines()

    # Match JS/TS test declarations
    js_test_re = re.compile(r"""^\s*(it|test)\(\s*['"]""")
    # Match Python test declarations
    py_test_re = re.compile(r"""^\s*def\s+(test_\w+)\s*\(""")
    # Match comment lines (JS/TS/Python)
    comment_re = re.compile(r"""^\s*(//|#|\*|/\*\*)""")

    for i, line in enumerate(lines):
        is_test = js_test_re.search(line) or py_test_re.search(line)
        if not is_test:
            continue

        # Look backwards for a comment within the preceding 3 lines
        has_comment = False
        for j in range(max(0, i - 3), i):
            if comment_re.search(lines[j]):
                has_comment = True
                break

        if not has_comment:
            findings.append(
                Finding(
                    file=file,
                    line=i + 1,
                    rule="missing-test-comment",
                    message="Test has no preceding comment justifying its efficacy",
                    severity="warning",
                )
            )

    return findings


def lint(root: str = ".") -> list[Finding]:
    """Run all static checks across all test files in the repo. No diff needed."""
    import os

    findings = []
    test_files = _find_test_files(root)

    for rel_path in test_files:
        full_path = os.path.join(root, rel_path)
        try:
            with open(full_path, "r") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError):
            continue

        lines = content.splitlines()

        # Run pattern checks against each line
        for line_num, line_content in enumerate(lines, 1):
            for pattern_def in LINT_PATTERNS:
                if pattern_def.get("needs_context"):
                    continue  # handled by _check_mock_assertions
                if re.search(pattern_def["pattern"], line_content):
                    findings.append(
                        Finding(
                            file=rel_path,
                            line=line_num,
                            rule=pattern_def["id"],
                            message=pattern_def["message"],
                            severity=pattern_def["severity"],
                        )
                    )

        # Contextual checks
        findings.extend(_check_mock_assertions(content, rel_path))
        findings.extend(_check_test_comments(content, rel_path))

    return findings


def collect_test_samples(root: str = ".") -> str:
    """Collect test functions with their preceding comments for LLM validation.

    Returns a formatted string of test samples: comment + test signature + assertions.
    Keeps it concise — only includes tests that have comments (lint catches missing ones).
    """
    import os

    samples = []
    test_files = _find_test_files(root)

    js_test_re = re.compile(r"""^\s*(it|test)\(\s*['"]""")
    py_test_re = re.compile(r"""^\s*def\s+(test_\w+)\s*\(""")
    comment_re = re.compile(r"""^\s*(//|#)""")
    assert_re = re.compile(r"""^\s*(expect|assert)\b""")

    for rel_path in test_files:
        full_path = os.path.join(root, rel_path)
        try:
            with open(full_path, "r") as f:
                lines = f.readlines()
        except (OSError, UnicodeDecodeError):
            continue

        for i, line in enumerate(lines):
            is_test = js_test_re.search(line) or py_test_re.search(line)
            if not is_test:
                continue

            # Collect preceding comment (up to 3 lines back)
            comment_lines = []
            for j in range(max(0, i - 3), i):
                if comment_re.search(lines[j]):
                    comment_lines.append(lines[j].rstrip())

            if not comment_lines:
                continue  # Lint handles missing comments

            # Collect assertions from the test body (up to 20 lines forward)
            assertion_lines = []
            for j in range(i + 1, min(len(lines), i + 20)):
                stripped = lines[j].strip()
                if assert_re.search(stripped):
                    assertion_lines.append(f"  {stripped}")
                # Stop at next test or closing brace at indent level
                if js_test_re.search(lines[j]) or py_test_re.search(lines[j]):
                    break

            sample = f"File: {rel_path}:{i + 1}\n"
            sample += "\n".join(comment_lines) + "\n"
            sample += line.rstrip() + "\n"
            if assertion_lines:
                sample += "Assertions:\n" + "\n".join(assertion_lines)
            else:
                sample += "Assertions: (none found)"
            samples.append(sample)

    # Cap to avoid huge prompts — sample up to 50
    if len(samples) > 50:
        import random
        random.seed(42)
        samples = random.sample(samples, 50)

    return "\n\n---\n\n".join(samples)


def format_findings(findings: list[Finding]) -> str:
    """Format static findings for inclusion in prompts."""
    if not findings:
        return "No static check findings."

    lines = ["Static analysis found the following issues in test files:\n"]
    for f in findings:
        lines.append(f"- [{f.severity.upper()}] `{f.file}:{f.line}` — {f.message}")
    return "\n".join(lines)
