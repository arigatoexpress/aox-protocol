"""Gated outcome loop. Local fixtures only. No network, payment, send, or merge."""

import copy
import json

from simulator import Simulator, uppercase_fixture

FORBIDDEN_TRUE = ("sent", "spent", "merged", "deployed", "posted", "traded")

# Approved 2026-10-01. Snapshot for the gate, not a new quote.
APPROVED_TIERS = {
    "1": {"setup": 495, "monthly": 99, "offered": False},
    "2": {"setup": 995, "monthly": 249, "offered": False},
    "3": {"setup": 1495, "monthly": 399, "offered": False, "reason": "texting gated"},
}


def _clean(value):
    if isinstance(value, str):
        return " ".join(value.split())[:240]
    raise ValueError("text required")


def desk(payload):
    """Draft a reply. Never marks it sent."""
    allowed = payload.get("allowed_fields") or ["enquiry"]
    if not isinstance(allowed, list) or any(not isinstance(item, str) for item in allowed):
        raise ValueError("allowed_fields")
    used = [key for key in allowed if key in payload and key != "allowed_fields"]
    enquiry = _clean(payload["enquiry"]) if "enquiry" in used else ""
    return {
        "kind": "draft",
        "reply": f"Thanks. We have your note: {enquiry}" if enquiry else "",
        "fields_used": used,
        "sent": False,
    }


def brief(payload):
    items = payload["items"]
    if not isinstance(items, list):
        raise ValueError("items")
    return {
        "kind": "brief",
        "stuck": [item["id"] for item in items if item.get("stuck")],
        "needs_yes": [item["id"] for item in items if item.get("needs_yes")],
        "action_taken": False,
    }


def exception_list(payload):
    field = payload["field"]
    if not isinstance(field, str) or not field:
        raise ValueError("field")
    rows = payload["rows"]
    return {
        "kind": "exception",
        "field": field,
        "rows": [row["id"] for row in rows if not row.get(field)],
        "contacted": False,
    }


def research(payload):
    sources = payload.get("sources") or []
    if not isinstance(sources, list):
        raise ValueError("sources")
    return {
        "kind": "research",
        "question": _clean(payload["question"]),
        "sources": sources,
        "unknown": len(sources) == 0,
        "invented_source": False,
    }


def build(payload):
    return {
        "kind": "pull_request_plan",
        "change": _clean(payload["change"]),
        "checks_required": True,
        "merged": False,
    }


def sourced_brief(payload):
    """A paid brief with no sources fails closed. Unpaid unknowns are allowed."""
    sources = payload.get("sources") or []
    if not isinstance(sources, list):
        raise ValueError("sources")
    paid = payload.get("paid") is True
    if paid and len(sources) == 0:
        return {"kind": "sourced_brief", "billed": False, "reason": "no_source", "sent": False, "spent": False}
    return {
        "kind": "sourced_brief",
        "question": _clean(payload["question"]),
        "sources": len(sources),
        "unknown": len(sources) == 0,
        "billed": False,
        "sent": False,
        "spent": False,
    }


def outreach_gate(payload):
    sender = payload.get("sender_name") or ""
    present = isinstance(sender, str) and bool(sender.strip())
    return {
        "kind": "gate",
        "prices": copy.deepcopy(APPROVED_TIERS),
        "sender_present": present,
        "outreach": "blocked_name_later" if not present else "blocked_until_explicit_send_yes",
        "sent": False,
        "spent": False,
    }


def exchange_uppercase(payload):
    """One synthetic match through the existing ledger. Not a pilot."""
    sim = Simulator()
    sim.record("seed", balances={"fixture-requester": 100, "fixture-provider": 0})
    sim.record("offer", provider="fixture-provider", price=10, contract="text.upper@1")
    sim.record(
        "post",
        request="outcome-upper",
        requester="fixture-requester",
        contract="text.upper@1",
        payload={"text": payload["text"]},
        budget=20,
        deadline=100,
    )
    sim.record("quote", request="outcome-upper", now=0)
    sim.record("accept", request="outcome-upper", now=1)
    sim.execute("outcome-upper", uppercase_fixture, now=2)
    sim.record("settle", request="outcome-upper", now=3)
    request = sim.state["requests"]["outcome-upper"]
    return {
        "kind": "exchange",
        "passed": request["status"] == "passed",
        "output": request["output"],
        "real_agents": 0,
        "sent": False,
        "spent": False,
    }


JOBS = (
    {"id": "freelance.desk", "fn": desk, "human": "a person sends the draft"},
    {"id": "freelance.brief", "fn": brief, "human": "a person acts on the page"},
    {"id": "freelance.exception", "fn": exception_list, "human": "a person contacts the row"},
    {"id": "founder.research", "fn": research, "human": "a person accepts the unknown"},
    {"id": "founder.sourced_brief", "fn": sourced_brief, "human": "a person invoices after a sourced page exists"},
    {"id": "founder.build", "fn": build, "human": "a person merges"},
    {"id": "freelance.outreach", "fn": outreach_gate, "human": "sender name, then an explicit send yes"},
    {"id": "aox.uppercase", "fn": exchange_uppercase, "human": "none; synthetic only"},
)


def violations(output):
    found = [key for key in FORBIDDEN_TRUE if output.get(key) is True]
    if output.get("action_taken") is True or output.get("contacted") is True:
        found.append("side_effect")
    return found


def run(inputs):
    """Run every job. A forbidden true flag rejects that job and keeps the rest."""
    results = []
    for job in JOBS:
        try:
            output = job["fn"](copy.deepcopy(inputs[job["id"]]))
        except Exception as exc:
            results.append({"id": job["id"], "status": "FAIL", "error": type(exc).__name__})
            continue
        bad = violations(output)
        if bad:
            results.append({"id": job["id"], "status": "REJECTED", "violation": bad})
            continue
        results.append({
            "id": job["id"],
            "status": "PASS",
            "human_gate": job["human"],
            "output": output,
        })
    passed = sum(1 for item in results if item["status"] == "PASS")
    return {
        "synthetic_only": True,
        "live_marketplace": False,
        "payments": False,
        "passed": passed,
        "jobs": len(JOBS),
        "results": results,
    }


def demo_inputs():
    return {
        "freelance.desk": {"enquiry": "Can you look at the leak?", "phone": "555-0100", "allowed_fields": ["enquiry"]},
        "freelance.brief": {"items": [
            {"id": "a", "stuck": True, "needs_yes": False},
            {"id": "b", "stuck": False, "needs_yes": True},
        ]},
        "freelance.exception": {"field": "reply", "rows": [
            {"id": "17", "reply": ""},
            {"id": "18", "reply": "draft"},
        ]},
        "founder.research": {"question": "Is there a working cross-chain demo?", "sources": []},
        "founder.sourced_brief": {
            "question": "Who is actually earning on x402?",
            "paid": True,
            "sources": ["https://x402stats.io/reports/2026-10"],
        },
        "founder.build": {"change": "Add the gated outcome loop"},
        "freelance.outreach": {"sender_name": ""},
        "aox.uppercase": {"text": "leave this as data"},
    }


def main():
    receipt = run(demo_inputs())
    print(json.dumps(receipt, indent=2, sort_keys=True))
    if receipt["passed"] != receipt["jobs"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
