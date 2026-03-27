# test-guardian

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**LLMs write bad tests and say they're done. This makes them do it properly.**

test-guardian forks your Claude Code session, challenges it through an escalating review loop, and doesn't let it declare completion until the tests actually prove something. It mechanises the human challenge that breaks the pattern — "is this actually ready for review?" — so you don't have to ask every time.

The core insight: LLMs *can* identify their own test quality gaps when challenged. They just don't do it unprompted. Five documented instances (including one where the LLM was shown its own failure history and still repeated the pattern) prove that self-awareness doesn't fix the behaviour. Mechanical enforcement does.

---

## The problem

Every LLM coding assistant does this:

1. You ask for tests
2. It writes leaf-only unit tests with tautological assertions
3. It declares done — "43 new tests, 529 total, 0 failures"
4. You ask "is that actually complete?"
5. It finds its own gaps — integration paths untested, mocks not wired, error paths missing
6. Repeat steps 4-5 until acceptable

The cycle has a deeper property: **it survives meta-awareness**. Showing the LLM its documented failure history, having it acknowledge the pattern, getting explicit commitment to avoid it — and it immediately repeats steps 2-3. Knowledge of the problem does not interrupt the problem.

See [PROBLEM.md](PROBLEM.md) for the full analysis with five documented instances.

## How it works

```
/guardian
    │
    ├─ Static checks (regex, zero cost)
    │   └─ Tautological assertions, existence-only checks, empty tests
    │
    ├─ Fork session (inherits full parent context)
    │
    ├─ Phase 1: "Write tests"
    │   ├─ Prescriptive criteria (assert on behaviour, not existence)
    │   ├─ 3rd party examination framing
    │   └─ Scepticism warning (we know you tend to shortcut this)
    │
    ├─ Phase 2: "Have you completed to the prescribed standard?"
    │   └─ Loop until session confirms
    │
    ├─ Phase 2.5: Quality gate
    │   ├─ Tier 1: Lint (mechanical) — missing comments, tautological patterns
    │   └─ Tier 2: LLM validation — do // Verifies: comments match assertions?
    │   └─ Loop until both tiers pass
    │
    ├─ Phase 3: "About to submit for review. Confident of a pass?"
    │   └─ Loop until confident with no gaps
    │
    └─ Report back to parent session (context stays clean)
```

**All test work happens in the fork.** The parent session's context window is never consumed by test iteration churn. The fork is disposable.

**Loop control is external.** A Python script decides when to continue — neither the LLM writing the tests nor the LLM confirming quality controls the loop. This prevents the completion pressure that causes the problem.

**The `// Verifies:` comment** may be the single highest-impact mechanism. It forces the LLM to articulate what each test proves *at write time*. It's much harder to write `// Verifies: the function exists` followed by `expect(result).toBeDefined()` than to just write the assertion alone.

## Usage

```bash
# From any Claude Code session:
/guardian              # review tests for staged/uncommitted changes
/guardian --all        # review full test suite
/guardian --lint       # static checks only, no LLM (fast)
/guardian --base main  # review tests against a branch
```

### Standalone lint

```bash
# Run static checks against any project's test files:
python3 /path/to/test-guardian/guardian.py --lint
```

Catches without any LLM cost:
- `expect(true).toBe(true)` — tautological assertions
- `.toBeDefined()` / `.toBeTruthy()` — existence-only checks
- `.not.toThrow()` — no-throw-only assertions
- `assert True` / `assert x is not None` — Python equivalents
- Empty test bodies
- Mocks created without corresponding assertions
- Tests missing `// Verifies:` efficacy comments

## Install

```bash
git clone https://github.com/jimovonz/test-guardian
cd test-guardian
bash install.sh
```

This symlinks the `/guardian` slash command into `~/.claude/commands/`.

### Requirements

- Python 3.10+
- Claude Code CLI (`claude`)
- Git

No other dependencies. Python stdlib only.

## The prescriptive standard

The reviewer enforces a specific, non-negotiable standard:

> For every non-trivial code path changed or added, there must be at least one test that would fail if its behaviour regressed.

Specifically:

1. **Assert on behaviour, not existence.** `expect(result).toBe(42)`, not `expect(result).toBeDefined()`
2. **Exercise integration paths, not just leaves.** Test the flow through A→B→C, not just C in isolation
3. **Mock only external boundaries.** APIs, databases, filesystem. Never mock internal functions
4. **Include error and edge cases.** At least one error path per public function
5. **Every test needs a `// Verifies:` comment.** State what the test proves. If you can't articulate it, the test is shallow
6. **Accepted gaps must be documented.** `// TEST-GUARDIAN: <reason>` for coverage omitted due to disproportionate mocking effort

The default posture is strict — missing coverage is a finding. Cost-benefit is a defence the session can make, not a default exemption.

## Why fork-based

The fork (`claude -p --continue --fork-session`) inherits the parent session's full conversation context for free — every file read, every code change, every decision. The forked session doesn't need to rediscover the project. It already knows what was written and why.

This is also token-cost-neutral. The test iteration context would have been generated in the parent session anyway — it's just redirected to a disposable fork. The parent session stays lean for continued development.

## Paired with

- [Cairn](https://github.com/jimovonz/cairn) — persistent memory for Claude Code. Memories about test quality failures across sessions informed the design of test-guardian
- [claude-assist](https://github.com/jimovonz/claude-assist) — multi-channel Claude Code access. The five documented test quality failures that motivated this project all occurred in claude-assist development

## License

[MIT](LICENSE)
