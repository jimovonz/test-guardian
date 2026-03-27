#!/usr/bin/env python3
"""Test Guardian — orchestrates an escalating test quality review loop.

Forks the current Claude Code session, replays a challenge playbook,
and returns a report. All test work happens in the fork; the parent
session's context stays clean.
"""

import argparse
import json
import re
import subprocess
import sys
import time

import prompts
import report
import static_checks


DEFAULT_MAX_ITER = 3
FORK_TIMEOUT = 600  # 10 minutes per LLM call


class ForkSession:
    """Manages a persistent forked Claude Code session."""

    def __init__(self, permission_mode: str = "auto"):
        self.session_id: str | None = None
        self.permission_mode = permission_mode
        self.responses: list[str] = []

    def send(self, prompt: str) -> str:
        """Send a prompt to the forked session and return the response."""
        cmd = ["claude", "-p", "--output-format", "json"]

        if self.session_id is None:
            # First call — fork from parent session
            cmd += ["--continue", "--fork-session", "--no-session-persistence"]
        else:
            # Subsequent calls — resume the fork
            cmd += ["--resume", self.session_id]

        cmd += ["--permission-mode", self.permission_mode]
        cmd.append(prompt)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=FORK_TIMEOUT,
        )

        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"Claude fork failed (exit {result.returncode}): {error_msg}")

        output = json.loads(result.stdout)

        # Capture session ID from first response for subsequent calls
        if self.session_id is None:
            self.session_id = output.get("session_id")

        response_text = output.get("result", "")
        self.responses.append(response_text)
        return response_text


def get_diff(base: str | None = None, all_mode: bool = False) -> str:
    """Get the diff or file list to review."""
    if all_mode:
        # List all test files in the repo
        result = subprocess.run(
            ["git", "ls-files"],
            capture_output=True,
            text=True,
        )
        files = result.stdout.strip().splitlines()
        test_files = [
            f
            for f in files
            if any(
                p in f
                for p in ["test", "spec", "_test.", ".test.", "tests/", "__tests__/"]
            )
        ]
        if not test_files:
            return ""
        # Also list source files for context
        return "Test files:\n" + "\n".join(test_files) + "\n\nSource files:\n" + "\n".join(
            f for f in files if f not in test_files and not f.startswith(".")
        )

    if base:
        result = subprocess.run(
            ["git", "diff", f"{base}...HEAD"],
            capture_output=True,
            text=True,
        )
        return result.stdout

    # Default: staged + unstaged
    staged = subprocess.run(
        ["git", "diff", "--cached"],
        capture_output=True,
        text=True,
    )
    unstaged = subprocess.run(
        ["git", "diff"],
        capture_output=True,
        text=True,
    )
    return (staged.stdout + "\n" + unstaged.stdout).strip()


def extract_json(text: str) -> dict | None:
    """Extract a JSON object from LLM response text."""
    # Try to find JSON in code blocks first
    code_block = re.search(r"```(?:json)?\s*\n?({.*?})\s*\n?```", text, re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find raw JSON object
    json_match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    return None


def main():
    parser = argparse.ArgumentParser(description="Test Guardian — escalating test quality review")
    parser.add_argument("--all", action="store_true", help="Review full test suite")
    parser.add_argument("--lint", action="store_true", help="Run static checks only (no LLM)")
    parser.add_argument("--base", type=str, help="Diff against branch (e.g. main)")
    parser.add_argument("--max-iter", type=int, default=DEFAULT_MAX_ITER, help="Max iterations per phase")
    args = parser.parse_args()

    # Lint mode: static checks only, no LLM
    if args.lint:
        findings = static_checks.lint()
        if not findings:
            print("# Test Guardian Lint: CLEAN\n\nNo issues found.")
        else:
            print(f"# Test Guardian Lint: {len(findings)} finding(s)\n")
            print(static_checks.format_findings(findings))
        sys.exit(1 if findings else 0)

    # Get diff
    scope_mode = "all" if args.all else "diff"
    diff = get_diff(base=args.base, all_mode=args.all)

    if not diff and not args.all:
        print("No changes to review.")
        sys.exit(0)

    # Phase 0: Static checks
    static_findings = []
    if not args.all:
        static_findings = static_checks.run(diff)
    static_text = static_checks.format_findings(static_findings)

    # Track progress
    phases = []
    start_time = time.time()

    # Create forked session
    session = ForkSession()

    # Phase 1: Write tests
    print("Phase 1: Writing tests...", file=sys.stderr)
    phase1_prompt = prompts.build_write_tests(diff, static_text, scope_mode)
    phase1_response = session.send(phase1_prompt)
    phases.append({
        "phase": 1,
        "name": "Write tests",
        "response": phase1_response,
    })

    # Phase 2: Confirm completion
    print("Phase 2: Confirming completion...", file=sys.stderr)
    phase2_iterations = 0
    for i in range(args.max_iter):
        phase2_iterations += 1
        phase2_prompt = prompts.build_confirm_complete()
        phase2_response = session.send(phase2_prompt)

        result = extract_json(phase2_response)
        if result and result.get("complete", False):
            phases.append({
                "phase": 2,
                "name": "Confirm completion",
                "iterations": phase2_iterations,
                "result": result,
            })
            break

        # Session identified remaining work — it will continue on next prompt
        phases.append({
            "phase": 2,
            "name": f"Completion check (iteration {phase2_iterations})",
            "result": result,
            "response": phase2_response,
        })

    # Phase 3: Confidence check
    print("Phase 3: Confidence check...", file=sys.stderr)
    phase3_iterations = 0
    final_confident = False
    final_gaps = []

    for i in range(args.max_iter):
        phase3_iterations += 1
        phase3_prompt = prompts.build_confident_of_pass()
        phase3_response = session.send(phase3_prompt)

        result = extract_json(phase3_response)
        if result:
            if result.get("confident", False) and not result.get("gaps"):
                final_confident = True
                phases.append({
                    "phase": 3,
                    "name": "Confidence check",
                    "iterations": phase3_iterations,
                    "result": result,
                })
                break

            final_gaps = result.get("gaps", [])
            phases.append({
                "phase": 3,
                "name": f"Confidence check (iteration {phase3_iterations})",
                "result": result,
                "response": phase3_response,
            })
        else:
            # Couldn't parse JSON — treat as not confident
            phases.append({
                "phase": 3,
                "name": f"Confidence check (iteration {phase3_iterations})",
                "result": {"confident": False, "parse_error": True},
                "response": phase3_response,
            })

    elapsed = time.time() - start_time

    # Generate report
    print(
        report.format_report(
            phases=phases,
            static_findings=static_findings,
            final_confident=final_confident,
            final_gaps=final_gaps,
            elapsed=elapsed,
            scope_mode=scope_mode,
        )
    )


if __name__ == "__main__":
    main()
