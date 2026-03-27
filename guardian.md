---
description: Write and validate test coverage through escalating review
---

Run the test guardian orchestrator. This forks your current session to write tests, then challenges it through escalating review stages until confident of quality.

```bash
python3 /home/james/Projects/test-guardian/guardian.py $ARGUMENTS
```

Options:
- (no args) — review tests for staged/uncommitted changes
- `--all` — review full test suite
- `--lint` — static checks only, no LLM (fast, checks all test files)
- `--base main` — review tests for changes since main
- `--max-iter 3` — max iterations per phase (default 3)

Wait for the script to complete and display the report to the user.
