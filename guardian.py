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

    def __init__(self, permission_mode: str = "bypassPermissions"):
        self.session_id: str | None = None
        self.permission_mode = permission_mode
        self.responses: list[str] = []

    def send(self, prompt: str) -> str:
        """Send a prompt to the forked session and return the response."""
        cmd = ["claude", "-p", "--output-format", "json"]

        if self.session_id is None:
            # First call — fork from parent session
            # Note: cannot use --no-session-persistence here — subsequent
            # calls need to --resume the session, which requires persistence
            cmd += ["--continue", "--fork-session"]
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
        # Strip cairn memory blocks from response if present
        response_text = re.sub(r"<memory>.*?</memory>", "", response_text, flags=re.DOTALL).strip()
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

    # Phase 2.5: Two-tier quality gate (lint + LLM comment validation)
    print("Phase 2.5: Quality gate...", file=sys.stderr)
    gate_iterations = 0
    for i in range(args.max_iter):
        gate_iterations += 1

        # Tier 1: Mechanical lint
        lint_findings = static_checks.lint()
        if lint_findings:
            lint_text = static_checks.format_findings(lint_findings)
            print(f"  Lint: {len(lint_findings)} finding(s), sending back...", file=sys.stderr)
            gate_prompt = prompts.build_lint_gate(lint_text)
            gate_response = session.send(gate_prompt)
            phases.append({
                "phase": 2.5,
                "name": f"Lint gate (iteration {gate_iterations})",
                "lint_findings": len(lint_findings),
                "response": gate_response,
            })
            continue  # Re-lint after fixes

        # Tier 2: LLM comment-assertion validation (separate cheap call)
        print("  Lint clean. Validating comment-assertion alignment...", file=sys.stderr)
        test_samples = static_checks.collect_test_samples()
        if test_samples:
            validation_prompt = prompts.build_comment_validation(test_samples)
            validation_response = session.send(validation_prompt)
            validation_result = extract_json(validation_response)

            if validation_result and validation_result.get("mismatches"):
                phases.append({
                    "phase": 2.5,
                    "name": f"Comment validation (iteration {gate_iterations})",
                    "result": validation_result,
                    "response": validation_response,
                })
                continue  # Session fixes mismatches, re-validate

        phases.append({
            "phase": 2.5,
            "name": "Quality gate passed",
            "iterations": gate_iterations,
        })
        break

    # Phase 3: Confidence check
    print("Phase 3: Confidence check...", file=sys.stderr)
    phase3_iterations = 0
    final_confident = False
    final_gaps = []
    phase3_raw_responses = []

    for i in range(args.max_iter):
        phase3_iterations += 1

        if i == 0:
            phase3_prompt = prompts.build_confident_of_pass()
        else:
            # Previous response didn't contain JSON — demand it
            phase3_prompt = prompts.build_json_enforcement(phase3_raw_responses[-1])

        phase3_response = session.send(phase3_prompt)
        phase3_raw_responses.append(phase3_response)

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
            print(f"  No JSON in response, enforcing format...", file=sys.stderr)
            # Don't append a phase entry yet — we'll retry with enforcement

    # If we exhausted iterations without JSON, include all raw responses
    if not final_confident and not final_gaps:
        phases.append({
            "phase": 3,
            "name": "Confidence check (raw output)",
            "response": "\n\n---\n\n".join(phase3_raw_responses),
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
