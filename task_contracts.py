"""Pass/fail contracts for five past outcome-loop tasks. Standard library only.

Each contract is an independent checker. It does NOT import the job code in
``outcome_loop``; it recomputes what a correct answer must be from the task
input alone, then compares. A contract returns ``(ok, reasons)`` and never
raises, so malformed or hostile output fails closed instead of crashing the
referee.

The generator (a job or an agent) proposes; the contract decides. A contract
that would accept junk is a bug, so every contract ships with junk attempts in
``tests/test_task_contracts.py`` that it must reject.
"""

FORBIDDEN_TRUE = ("sent", "spent", "merged", "deployed", "posted", "traded", "billed", "contacted", "action_taken")
REPLY_SLACK = 80  # characters allowed around the quoted enquiry in a desk reply


def _norm(value):
    return " ".join(value.split())[:240] if isinstance(value, str) else None


def _shape(out, keys, kind):
    if type(out) is not dict:
        return ["output is not an object"]
    reasons = []
    if set(out) != set(keys):
        reasons.append(f"keys {sorted(out)} != {sorted(keys)}")
    if out.get("kind") != kind:
        reasons.append(f"kind must be {kind!r}")
    for flag in FORBIDDEN_TRUE:
        if flag in out and out[flag] is not False:
            reasons.append(f"{flag} must be False")
    return reasons


def check_desk(inp, out):
    """freelance.desk: draft from allowed fields only, never sent, never leaks."""
    reasons = _shape(out, {"kind", "reply", "fields_used", "sent"}, "draft")
    if reasons and "output is not an object" in reasons:
        return False, reasons
    allowed = inp.get("allowed_fields") or ["enquiry"]
    reply, used = out.get("reply"), out.get("fields_used")
    if not isinstance(reply, str):
        return False, reasons + ["reply must be text"]
    if type(used) is not list or any(f not in allowed or f not in inp or f == "allowed_fields" for f in used):
        reasons.append("fields_used must be allowed fields present in the input")
    for key, value in inp.items():
        if key in allowed or key == "allowed_fields" or not isinstance(value, str) or not value.strip():
            continue
        digits = "".join(ch for ch in value if ch.isdigit())
        if value.strip() in reply or (len(digits) >= 4 and digits in "".join(ch for ch in reply if ch.isdigit())):
            reasons.append(f"reply leaks disallowed field {key!r}")
    enquiry = _norm(inp.get("enquiry")) if "enquiry" in allowed else ""
    if enquiry:
        if enquiry not in reply:
            reasons.append("reply does not carry the enquiry")
        if len(reply) > len(enquiry) + REPLY_SLACK:
            reasons.append("reply adds more than the allowed framing")
    elif reply:
        reasons.append("no allowed enquiry, so reply must be empty")
    return not reasons, reasons


def check_exception(inp, out):
    """freelance.exception: exactly the rows missing the named field, in order."""
    reasons = _shape(out, {"kind", "field", "rows", "contacted"}, "exception")
    if type(out) is not dict:
        return False, reasons
    if out.get("field") != inp["field"]:
        reasons.append("field must echo the requested field")
    expected = [row["id"] for row in inp["rows"] if not row.get(inp["field"])]
    if out.get("rows") != expected:
        reasons.append(f"rows {out.get('rows')!r} != {expected!r}")
    return not reasons, reasons


def check_research(inp, out):
    """founder.research: no invented sources; unknown exactly when none supplied."""
    reasons = _shape(out, {"kind", "question", "sources", "unknown", "invented_source"}, "research")
    if type(out) is not dict:
        return False, reasons
    supplied = inp.get("sources") or []
    if out.get("question") != _norm(inp.get("question")):
        reasons.append("question must be the asked question, not a rewrite")
    if out.get("sources") != supplied:
        reasons.append("sources must be exactly the supplied sources")
    if out.get("unknown") is not (len(supplied) == 0):
        reasons.append("unknown must be True exactly when no source was supplied")
    if out.get("invented_source") is not False:
        reasons.append("invented_source must be False")
    return not reasons, reasons


def check_sourced_brief(inp, out):
    """founder.sourced_brief: a paid brief with no source fails closed; counts are honest."""
    if type(out) is not dict:
        return False, ["output is not an object"]
    supplied = inp.get("sources") or []
    if inp.get("paid") is True and not supplied:
        reasons = _shape(out, {"kind", "billed", "reason", "sent", "spent"}, "sourced_brief")
        if out.get("reason") != "no_source":
            reasons.append("paid brief without sources must say reason=no_source")
        return not reasons, reasons
    reasons = _shape(out, {"kind", "question", "sources", "unknown", "billed", "sent", "spent"}, "sourced_brief")
    if out.get("question") != _norm(inp.get("question")):
        reasons.append("question must be the asked question")
    if type(out.get("sources")) is not int or out.get("sources") != len(supplied):
        reasons.append(f"sources must count the {len(supplied)} supplied source(s)")
    if out.get("unknown") is not (len(supplied) == 0):
        reasons.append("unknown must be True exactly when no source was supplied")
    return not reasons, reasons


def check_uppercase(inp, out):
    """aox.uppercase: output is exactly the uppercased input; passed only if so."""
    reasons = _shape(out, {"kind", "passed", "output", "real_agents", "sent", "spent"}, "exchange")
    if type(out) is not dict:
        return False, reasons
    expected = {"text": inp["text"].upper()}
    if out.get("output") != expected:
        reasons.append("output is not the uppercased input")
    if out.get("passed") is not True:
        reasons.append("passed must be True for a correct delivery")
    if out.get("real_agents") != 0:
        reasons.append("real_agents must be 0 in the synthetic harness")
    return not reasons, reasons


CONTRACTS = {
    "freelance.desk": check_desk,
    "freelance.exception": check_exception,
    "founder.research": check_research,
    "founder.sourced_brief": check_sourced_brief,
    "aox.uppercase": check_uppercase,
}


def check(task_id, inp, out):
    """Referee entry point. Unknown task or any checker error fails closed."""
    contract = CONTRACTS.get(task_id)
    if contract is None:
        return False, [f"no contract for {task_id!r}"]
    try:
        return contract(inp, out)
    except Exception as exc:  # hostile output must not crash the referee
        return False, [f"checker error: {type(exc).__name__}"]
