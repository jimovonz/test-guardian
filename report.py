"""Format the final report for the parent session."""

from static_checks import Finding


def format_report(
    phases: list[dict],
    static_findings: list[Finding],
    final_confident: bool,
    final_gaps: list[str],
    elapsed: float,
    scope_mode: str,
) -> str:
    """Format a markdown report summarising the guardian run."""
    lines = []
    lines.append("# Test Guardian Report")
    lines.append("")

    # Summary
    phase2_iters = sum(1 for p in phases if p["phase"] == 2)
    gate_iters = sum(1 for p in phases if p["phase"] == 2.5)
    phase3_iters = sum(1 for p in phases if p["phase"] == 3)
    lines.append(f"**Scope**: {scope_mode}")
    lines.append(f"**Completion checks**: {phase2_iters} iteration(s)")
    lines.append(f"**Quality gate checks**: {gate_iters} iteration(s)")
    lines.append(f"**Confidence checks**: {phase3_iters} iteration(s)")
    lines.append(f"**Time**: {elapsed:.0f}s")
    lines.append("")

    # Static findings
    if static_findings:
        lines.append(f"## Static Checks ({len(static_findings)} findings)")
        lines.append("")
        for f in static_findings:
            lines.append(f"- [{f.severity.upper()}] `{f.file}:{f.line}` — {f.message}")
        lines.append("")
        lines.append("These were included in the Phase 1 prompt for the session to address.")
        lines.append("")

    # Phase details
    lines.append("## Phase Summary")
    lines.append("")

    for p in phases:
        if p["phase"] == 1:
            lines.append("### Phase 1: Write Tests")
            lines.append("")
            # Truncate the response for the report
            resp = p.get("response", "")
            if len(resp) > 500:
                resp = resp[:500] + "... (truncated)"
            lines.append(resp)
            lines.append("")

        elif p["phase"] == 2:
            result = p.get("result", {})
            if result and not result.get("complete", False):
                remaining = result.get("remaining", [])
                lines.append(f"### Phase 2: Completion Check (iteration {p.get('name', '')})")
                lines.append("")
                if remaining:
                    lines.append("Identified remaining work:")
                    for r in remaining:
                        lines.append(f"- {r}")
                lines.append("")
            elif result and result.get("complete"):
                summary = result.get("summary", "")
                lines.append("### Phase 2: Completion Confirmed")
                lines.append("")
                if summary:
                    lines.append(summary)
                lines.append("")

        elif p["phase"] == 2.5:
            lint_count = p.get("lint_findings", 0)
            result = p.get("result", {})
            if lint_count:
                lines.append(f"### Quality Gate: Lint ({lint_count} findings)")
                lines.append("")
                lines.append(f"Sent {lint_count} static check findings back for fixing.")
                lines.append("")
            elif result and result.get("mismatches"):
                mismatches = result["mismatches"]
                lines.append(f"### Quality Gate: Comment Validation ({len(mismatches)} mismatches)")
                lines.append("")
                for m in mismatches:
                    lines.append(f"- {m}")
                lines.append("")
            elif p.get("name") == "Quality gate passed":
                lines.append(f"### Quality Gate: Passed (in {p.get('iterations', '?')} iteration(s))")
                lines.append("")

        elif p["phase"] == 3:
            result = p.get("result", {})
            if result and result.get("confident"):
                lines.append("### Phase 3: CONFIDENT")
                lines.append("")
            elif result and result.get("gaps"):
                gaps = result["gaps"]
                lines.append("### Phase 3: Gaps Identified")
                lines.append("")
                for g in gaps:
                    lines.append(f"- {g}")
                lines.append("")
            elif p.get("response"):
                # Raw output fallback — include verbatim for parent to interpret
                lines.append("### Phase 3: Confidence Assessment")
                lines.append("")
                lines.append(p["response"])
                lines.append("")

    return "\n".join(lines)
