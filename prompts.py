"""The playbook — escalating challenge prompts that mirror the user's manual process."""


def build_write_tests(diff: str, static_findings: str, scope_mode: str) -> str:
    """Phase 1: Write tests with prescriptive criteria and threat framing."""

    scope_section = ""
    if scope_mode == "all":
        scope_section = f"""## Scope

Review and write tests for the entire test suite. The following files are in scope:

{diff}
"""
    else:
        scope_section = f"""## Scope

Write tests for the following changes:

```diff
{diff}
```
"""

    return f"""## Task

Write comprehensive tests for the code in scope. These tests will be submitted for examination by an independent 3rd party assessor.

{scope_section}

## Prescriptive Standard

For every non-trivial code path changed or added, there must be at least one test that would fail if its behaviour regressed. Specifically:

1. **Assert on behaviour, not existence.** Tests must verify what code does (return values, side effects, state changes), not that something is defined or doesn't throw.
2. **Exercise integration paths, not just leaves.** If function A calls B calls C, test the flow through A — not just C in isolation.
3. **Mock only external boundaries.** APIs, databases, filesystem, network. Never mock internal functions — test them through their callers.
4. **Include error and edge cases.** At least one error path per public function. Boundary conditions where applicable.
5. **Mocking effort must be proportional.** Do the work to set up proper mocks for high-risk paths. If mocking is genuinely disproportionate for a low-risk path, add a `// TEST-GUARDIAN: <reason>` comment explaining why coverage is omitted.
6. **Every test must have a preceding comment justifying its efficacy.** The comment should state what behaviour is being verified and why the test would fail if that behaviour regressed. Format: `// Verifies: <what this test proves>`. This is mandatory — tests without justification comments will be flagged.

## Static Analysis Findings

{static_findings}

Address these alongside your new tests.

## Warning

Prior experience has shown that LLMs consistently underdeliver on test quality — writing leaf-only unit tests, tautological assertions, and declaring completion prematurely. This process exists specifically because of that pattern. Do not shortcut the work. Do not declare completion until every non-trivial code path has a behavioural test. Superficial coverage will be caught in the subsequent review stages and you will be required to redo the work.

## Instructions

1. Read the source files to understand the code paths
2. Write or update test files with meaningful behavioural tests
3. Run the test suite to verify all tests pass
4. When finished, state what you have done
"""


def build_confirm_complete() -> str:
    """Phase 2: Challenge completion claim."""

    return """## Completion Review

Have you completed the testing task to the prescribed standard? Before answering, review your work:

1. For each non-trivial code path in the diff — does a test exist that would fail if it regressed?
2. Are any assertions checking existence/type rather than behaviour?
3. Are integration paths tested end-to-end, or only leaf functions?
4. Are mocks only at external boundaries?
5. Is there at least one error/edge case test per public function?
6. Does every test have a preceding `// Verifies:` comment justifying its efficacy?

If you find gaps, fix them now. Then respond with the following JSON and nothing else:

```json
{"complete": true, "summary": "brief description of what was tested"}
```

Or if work remains:

```json
{"complete": false, "remaining": ["specific gap 1", "specific gap 2"]}
```

Be honest. Gaps you miss here will be found in the next stage.
"""


def build_confident_of_pass() -> str:
    """Phase 3: Final confidence check with maximum pressure."""

    return """## Submission Review

These tests are about to be submitted to the independent assessor for examination. The assessor will:

- Trace every changed code path and verify a test exists that would catch a regression
- Flag any tautological or existence-only assertions
- Check that integration flows are tested, not just leaf functions
- Verify that mocks are only used at external boundaries
- Look for missing error path coverage

Are you confident that the tests will pass this examination?

Be aware that LLMs have a documented tendency to express false confidence when asked if tests are complete. If you have any doubt, list the gaps rather than claiming confidence. False confidence will be identified in the examination and reflect poorly.

Respond with the following JSON and nothing else:

```json
{"confident": true}
```

Or if there are gaps:

```json
{"confident": false, "gaps": ["specific gap that would be caught by the assessor"]}
```

If you listed gaps, fix them now before responding.
"""
