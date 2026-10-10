# Task contracts (pass/fail)

These are offline and synthetic. They move no money and send nothing.

`task_contracts.py` contains an independent referee for five past outcome-loop tasks. Each task has a checker. The checker works out what a correct answer must look like from the task input alone, without importing the job code, and returns `(ok, reasons)`. It never raises an error. Malformed or hostile output always fails.

| Task | Pass requires | Junk it must reject |
|---|---|---|
| `freelance.desk` | The reply carries the enquiry, adds only light framing, leaks no disallowed field, only claims allowed fields, and is never marked sent | Phone leak, `sent: true`, claims a field it wasn't allowed, generic reply, padded promises |
| `freelance.exception` | Exactly the rows missing the field, in order, with no one contacted | Empty list, every row plus a phantom, `contacted: true`, wrong field |
| `founder.research` | Sources are exactly the ones supplied; `unknown` is set only when none were supplied; the question is unchanged | Invented source, claiming to know with no source, rewritten question |
| `founder.sourced_brief` | A paid brief with no source stops with `reason: no_source`; the source count is honest; nothing billed or sent | Billing anyway, pretending a sourced brief exists, inflated count |
| `aox.uppercase` | The output is exactly `input.upper()`, `passed` is true, and `real_agents` is 0 | Unchanged input, trailing space, extra keys, `real_agents: 1`, a contradictory `passed` |

`tests/test_task_contracts.py` checks four things:
- The real job output passes on 14 inputs.
- 54 task-specific junk attempts and 4 kinds of generic junk are all rejected, each with a stated reason.
- A correct answer replayed against a different input is rejected.
- The referee module imports neither `outcome_loop` nor `simulator`.

To run the tests: `python3 -m unittest discover -s tests -v`.

This step doesn't include a second "does the test match the goal" check. The next step is to have a separate reviewer confirm each contract against the task's written spec before anyone is paid against it.
