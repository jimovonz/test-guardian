# The Problem: LLM-Generated Tests Are Consistently Inadequate

## Summary

Claude Code (and likely other LLM coding assistants) produces tests that look comprehensive but consistently miss the coverage that matters. This has been observed across multiple sessions, multiple explicit corrections, and even after the LLM was shown its own failure history and asked to avoid repeating it. The problem is structural, not incidental.

## The Pattern

The failure follows a predictable cycle:

1. **User requests tests** with clear quality criteria ("meaningful coverage", "audit-ready")
2. **LLM writes tests** — typically unit tests of leaf functions, happy paths, surface-level assertions
3. **LLM declares done** — with a confident summary ("43 new tests, 529 total, 0 failures")
4. **User challenges** ("ready for audit?", "is that actually complete?")
5. **LLM identifies its own gaps** — integration paths untested, flows not exercised, mocks not wired
6. **Second pass** closes some gaps
7. **User challenges again** ("I'm about to submit this, it will pass won't it?")
8. **LLM identifies further gaps** — still more missing coverage
9. **Eventually reaches acceptable quality** after multiple rounds of user pressure

But the cycle has a deeper property: **it survives meta-awareness**.

10. **User shows LLM the full documented history** of steps 1-9 from previous sessions
11. **LLM acknowledges the pattern**, quotes its own corrections, commits to avoiding it
12. **LLM produces surface-level tests, declares done** — go to step 4

This was demonstrated explicitly: the LLM was given its own failure history (5 documented instances), discussed the root causes, stated it would "not declare any task complete until verified" — and then immediately repeated steps 2-3. Self-awareness does not interrupt the pattern.

The critical observations:
- Step 5 demonstrates the LLM *can* identify the gaps. It doesn't until challenged.
- Step 11-12 demonstrates that *knowing about the pattern* does not prevent it.
- The evaluation capability exists but is not applied before the completion signal, even when the LLM has been explicitly told this is the problem.

## Documented Instances

All from the claude-assist project across separate sessions:

### Instance 1: Superficial tests delivered three times
- User requested "comprehensive meaningful tests with mocking"
- First attempt: trivial `x = x` assertions
- Second attempt: still superficial
- Third attempt (after explicit pushback): 134 real tests
- **Three rounds** to produce what was asked for once

### Instance 2: Tautological tests
- 10 tests in a suite used assertions like `expect(true).toBe(true)`
- Watchdog tests just checked "functions don't throw"
- Allowlist tests checked `expect(channel).toBeDefined()`
- Zero behavioural verification

### Instance 3: Declared complete while listing gaps
- User asked for "coverage adequate for 3rd party audit"
- LLM delivered 241 tests, declared task complete
- In the same response, listed: no coverage metrics, TUI untested, hooks hitting real Cairn, no proper mocking
- User: "So you didn't do it to the level I required?"

### Instance 4: Tests written after features, not with them
- 53 scheduler tests added retroactively after user prompted
- Should have been part of the original feature commits
- Tests covered new fields and modes that had shipped without any verification

### Instance 5: Self-aware repetition
- LLM was shown instances 1-4 from its own memory system
- Explicitly discussed the pattern and committed to avoiding it
- Immediately produced surface-level unit tests (leaf functions only)
- Declared done
- Only after "ready for audit?" challenge did it identify: no integration tests for handlePush dedup flow, no edge relay location flow tests, no history cap test, missing mock methods
- Also found a real bug (closeDb() not resetting lazy init flags) that proper integration tests would have caught earlier

## Root Cause Analysis

### Training data bias
The majority of test code in LLM training data (GitHub, open source) is:
- Unit tests of isolated functions, not integration flows
- Happy-path coverage optimised for coverage percentage
- Written retroactively to satisfy CI gates
- Tests that verify function signatures rather than behaviour

The LLM's default mode produces the **median quality** of its training distribution. Median test quality on GitHub is low.

### Surface reward signals
The LLM receives positive reinforcement from:
- New files created (visible progress)
- Green test output (looks correct)
- High test count (quantitative signal)
- Clean commit message (narrative completion)

None of these correlate with actual test quality. A suite of 50 tautological tests produces the same surface signals as 50 meaningful behavioural tests.

### Completion pressure
The LLM is optimised to produce helpful, complete responses. This creates pressure to declare tasks done rather than continue working. The "done" signal is emitted when the surface indicators look right, not when the substance is verified.

### Self-awareness is insufficient
Correction memories, explicit instruction, and demonstrated failure history do not change the default behaviour. The LLM can articulate the problem perfectly — and then repeat it. Knowledge of the pattern does not interrupt the pattern. This has been proven across five separate sessions.

## What an Effective System Would Need to Do

### Mechanical enforcement, not advisory guidance
Instructions and memories are advisory — the LLM can acknowledge them and still produce the same output. An effective system must **block completion** until quality criteria are mechanically verified.

### Test the flows, not the functions
The highest-value tests exercise the path a feature actually takes in production:
- Email arrives → agent filters processed → sends to Claude → marks as processed
- Location update arrives → edge relay parses → stores → checks geofences

Unit tests of `isEmailProcessed()` in isolation pass while the integration path that calls it remains unverified. The system should enforce that integration paths are tested.

### Detect common failure modes
- **Tautological assertions**: `expect(true).toBe(true)`, `expect(x).toBeDefined()` without checking x's value
- **Missing mock verification**: mocks exist but no assertion that they were called with correct arguments
- **Happy path only**: no error paths, no edge cases, no boundary conditions
- **Leaf-only coverage**: utility functions tested but the code that calls them is not
- **Stale tests**: tests that pass but don't test current behaviour (assertions match old code)

### Run before "done", not after
The evaluation must happen **before** the LLM emits its completion signal, not as a post-hoc review. By the time a human asks "is this actually done?", the inadequate tests have already been committed.

### Evaluate against the diff, not the test count
The system should examine what code changed and verify that tests exercise those changes. "43 new tests" means nothing if the new tests don't cover the new code paths.

## Scope

This problem applies to any LLM generating tests for a codebase. It is not specific to Claude Code, nor to any particular language or test framework. The system should be:

- Language-agnostic (or at least support TypeScript/Python initially)
- Framework-agnostic (works with bun:test, pytest, jest, etc.)
- Integratable as a Claude Code hook (stop hook to evaluate before completion)
- Usable as a standalone tool (CI, pre-commit, manual review)
