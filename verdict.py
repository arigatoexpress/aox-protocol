"""Three-state verdicts and the AOX receipt that carries one.

The ``Verdict`` enum is vendored from ``arigatoexpress/agentloop``
``agentloop/verdict.py`` (blob ``3b84a5a1898dabd770858f1e3a5d42e265a24b73``,
commit ``7c11eae8da7361fcfab099979374d91ef95d2cf3``). That repository is
private and had no LICENSE file on 2026-10-10. The enum is copied with
attribution; the receipt below is AOX lab code. The author relicenses the
vendored Verdict enum and the ported x402 rail under the Apache License 2.0.

Only OK is success. A missing, malformed, or timed-out referee result is
UNKNOWN. The receipt hash is an unkeyed SHA-256 over the other fields:
replayable and internally consistent. It does not authenticate an author.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum


class Verdict(str, Enum):
    """A lane run's outcome. There is deliberately no boolean form."""

    OK = "OK"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"

    @property
    def is_success(self) -> bool:
        """Only OK is success. UNKNOWN is never success — that is the whole point."""
        return self is Verdict.OK

    @property
    def counts_as_healthy(self) -> bool:
        """Alias kept explicit so call sites read as refusals, not truthiness."""
        return self is Verdict.OK


FORMAT = "aox-verdict-receipt@1"
_EVIDENCE = {"present", "missing", "malformed", "timed_out"}
_FIELDS = ("format", "provenance", "contract", "task_id", "verdict", "evidence", "reasons", "hash")


class TimedOutEvidence:
    """Marker for a referee window that closed with no answer."""


def verdict_for(evidence):
    """Map referee evidence to OK, FAILED, or UNKNOWN.

    ``(True, [])`` is OK. ``(False, [reasons...])`` is FAILED.
    ``None`` is missing. ``TimedOutEvidence`` or ``{"timed_out": True}`` is
    timed out. Anything else, including a truthy non-boolean, is malformed.
    Malformed success is UNKNOWN.
    """
    verdict, _kind, _reasons = _classify(evidence)
    return verdict


def build_receipt(task_id, evidence, contract):
    """Seal a synthetic receipt whose ``verdict`` field is the adapted result."""
    _identifier(task_id, "task_id")
    _identifier(contract, "contract")
    verdict, kind, reasons = _classify(evidence)
    body = {
        "format": FORMAT,
        "provenance": "synthetic",
        "contract": contract,
        "task_id": task_id,
        "verdict": verdict.value,
        "evidence": kind,
        "reasons": reasons,
    }
    body["hash"] = _digest(body)
    return body


def replay_receipt(receipt):
    """Recompute the receipt hash and check the verdict field against it.

    A full rewrite that carries a matching hash still replays. Callers that
    need authenticity need a verifier signature, which this lab receipt does
    not have.
    """
    if type(receipt) is not dict or set(receipt) != set(_FIELDS):
        raise ValueError("unsupported verdict receipt")
    if receipt["format"] != FORMAT or receipt["provenance"] != "synthetic":
        raise ValueError("only synthetic verdict receipts are supported")
    _identifier(receipt["task_id"], "task_id")
    _identifier(receipt["contract"], "contract")
    if receipt["evidence"] not in _EVIDENCE:
        raise ValueError("unknown evidence kind")
    reasons = receipt["reasons"]
    if type(reasons) is not list or len(reasons) > 32 or any(type(item) is not str or len(item) > 240 for item in reasons):
        raise ValueError("reasons are not a short list of strings")
    try:
        verdict = Verdict(receipt["verdict"])
    except ValueError as exc:
        raise ValueError("receipt verdict is not a three-state Verdict") from exc
    if receipt["evidence"] == "present":
        if verdict is Verdict.UNKNOWN:
            raise ValueError("present evidence cannot be UNKNOWN")
        if verdict is Verdict.OK and reasons:
            raise ValueError("OK cannot carry reasons")
    elif verdict is not Verdict.UNKNOWN or reasons:
        raise ValueError("missing evidence must be UNKNOWN")
    body = {key: receipt[key] for key in _FIELDS if key != "hash"}
    if receipt["hash"] != _digest(body) or type(receipt["hash"]) is not str:
        raise ValueError("verdict receipt hash mismatch")
    if verdict.is_success is not (verdict is Verdict.OK):
        raise ValueError("success bit drifted from OK")
    return receipt


def _classify(evidence):
    if evidence is None:
        return Verdict.UNKNOWN, "missing", []
    if isinstance(evidence, TimedOutEvidence):
        return Verdict.UNKNOWN, "timed_out", []
    if type(evidence) is dict and set(evidence) == {"timed_out"} and evidence["timed_out"] is True:
        return Verdict.UNKNOWN, "timed_out", []
    if type(evidence) is not tuple or len(evidence) != 2:
        return Verdict.UNKNOWN, "malformed", []
    ok, reasons = evidence
    if type(ok) is not bool or not _reason_list(reasons):
        return Verdict.UNKNOWN, "malformed", []
    if ok is True:
        if reasons:
            return Verdict.UNKNOWN, "malformed", []
        return Verdict.OK, "present", []
    return Verdict.FAILED, "present", list(reasons)


def _reason_list(reasons):
    return type(reasons) is list and len(reasons) <= 32 and all(type(item) is str and len(item) <= 240 for item in reasons)


def _identifier(value, label):
    if type(value) is not str or not value or len(value) > 128:
        raise ValueError(f"{label} must be a short string")


def _digest(body):
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()
