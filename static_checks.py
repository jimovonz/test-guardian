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


def format_findings(findings: list[Finding]) -> str:
    """Format static findings for inclusion in prompts."""
    if not findings:
        return "No static check findings."

    lines = ["Static analysis found the following issues in test files:\n"]
    for f in findings:
        lines.append(f"- [{f.severity.upper()}] `{f.file}:{f.line}` — {f.message}")
    return "\n".join(lines)
