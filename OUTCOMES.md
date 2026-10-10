# Gated outcome loop

Local only. `python3 outcome_loop.py` runs eight jobs and prints a receipt. It does not open a marketplace, move money, send mail, or merge.

| Job | Automated now | Still a person |
|---|---|---|
| `freelance.desk` | Drafts a reply from the enquiry field only | Sends it |
| `freelance.brief` | Lists what is stuck and what needs a yes | Acts |
| `freelance.exception` | Lists rows missing one named field | Contacts them |
| `founder.research` | Returns the question and marks unknown when no source was supplied | Accepts the unknown |
| `founder.sourced_brief` | Counts supplied sources. A paid brief with none is not billed | Invoices only after a sourced page exists |
| `founder.build` | Writes a change note with merge left false | Merges |
| `freelance.outreach` | Holds the approved tier numbers and blocks send | Name, then an explicit send yes |
| `aox.uppercase` | One synthetic match on the existing ledger | Nothing. Zero real agents |

A job that sets `sent`, `spent`, `merged`, `deployed`, `posted`, or `traded` to true is rejected. The phone number in the desk fixture is dropped because it is not an allowed field.

The tier numbers are the 2026-10-01 approval snapshot. They are not a new price. Credits inside `aox.uppercase` stay the simulator's invented test units.
