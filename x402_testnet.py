"""Base Sepolia x402 rail, simulated unless an injected settler is supplied.

Ported from the public archived repo ``arigatoexpress/agent-opportunity-exchange``
at commit ``8ef5daf676eea2934b4aa22657e94f6ab9429cd1``:

- ``src/x402-config.ts`` (blob ``afbf62a9438f497b777a7f797c6e620064cbe369``)
- ``src/x402-testnet.ts`` (blob ``e3f8e38c3f0f339967ec4eae51e8e273185c3b2c``)
- the client cap in ``scripts/x402-testnet-fetch.ts`` (blob ``c024c0b4``)

That repo had no LICENSE file on 2026-10-10. Env names accept the original
``AOE_`` keys and the ``AOX_`` names used here. The author relicenses this
ported rail under the Apache License 2.0. See ``payments/ATTRIBUTION.md``.

This module does not import the Hono middleware or the ``@x402`` packages and
never reads a private key from the process environment. A release requires a
replayed ``aox-verdict-receipt@1`` whose verdict is OK, a positive amount
inside the spend cap, and an allow-listed facilitator when the mode is
``x402_testnet``. Each receipt hash is consumed once on the supplied ledger.
``liveSettlementAllowed`` stays false. A settler runs only when the caller
injects one after that OK decision on Base Sepolia.
"""

import json
import re
from pathlib import Path

from verdict import Verdict, replay_receipt

BASE_SEPOLIA_NETWORK = "eip155:84532"
SOLANA_DEVNET_NETWORK = "solana-devnet"
DEFAULT_FACILITATOR_URL = "https://x402.org/facilitator"
ALLOWED_FACILITATORS = frozenset({DEFAULT_FACILITATOR_URL})
DEFAULT_SIMULATED_PAY_TO = "0x000000000000000000000000000000000000dEaD"
MAINNET_NETWORKS = frozenset({
    "eip155:8453",
    "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp",
    "stellar:pubnet",
})
HARD_CAP_MICROS = 5_000_000
DEFAULT_MAX_USD = "1.00"
_MODE_KEYS = ("AOX_PAYMENT_MODE", "AOE_PAYMENT_MODE")
_NETWORK_KEYS = ("AOX_X402_NETWORK", "AOE_X402_NETWORK", "AOX_TESTNET_NETWORK", "AOE_TESTNET_NETWORK")
_FACILITATOR_KEYS = ("AOX_X402_FACILITATOR_URL", "AOE_X402_FACILITATOR_URL", "X402_FACILITATOR_URL")
_PAY_TO_KEYS = ("AOX_X402_PAY_TO", "AOE_X402_PAY_TO", "EVM_PAY_TO")
_PRIVATE_KEY_KEYS = frozenset({
    "AOX_BUYER_EVM_PRIVATE_KEY",
    "AOE_BUYER_EVM_PRIVATE_KEY",
    "AOX_PRIVATE_KEY",
    "EVM_PRIVATE_KEY",
    "PRIVATE_KEY",
})
_KEY_VALUE = re.compile(r"^(?:0x)?[a-fA-F0-9]{64}$")
_AMOUNT = re.compile(r"^-?\d{1,18}$")
_PROCESS_LEDGER = None


class ReleaseLedger:
    """Hashes already released. A path stores those hashes and nothing else."""

    def __init__(self, path=None):
        self.path = path
        self._used = set()
        if path is not None:
            self._load()

    def consume(self, receipt_hash):
        if type(receipt_hash) is not str or not receipt_hash or receipt_hash in self._used:
            return False
        self._used.add(receipt_hash)
        self._store()
        return True

    def _load(self):
        file = Path(self.path)
        if not file.exists():
            return
        data = json.loads(file.read_text() or "[]")
        if type(data) is not list or any(type(item) is not str for item in data):
            raise ValueError("release ledger must be a list of hashes")
        self._used = set(data)

    def _store(self):
        if self.path is None:
            return
        Path(self.path).write_text(json.dumps(sorted(self._used), separators=(",", ":")))


def payment_status(env=None):
    """Return the rail status. The default mode is simulated and not ready."""
    env = {} if env is None else env
    errors = []
    warnings = []
    if _private_key_present(env):
        errors.append("private_key_refused")
    mode = _payment_mode(_pick(env, _MODE_KEYS, "simulated"), errors)
    network = _pick(env, _NETWORK_KEYS, BASE_SEPOLIA_NETWORK).strip()
    facilitator_url = _pick(env, _FACILITATOR_KEYS, DEFAULT_FACILITATOR_URL).strip().rstrip("/")
    pay_to = _pick(env, _PAY_TO_KEYS, "").strip()

    if network != BASE_SEPOLIA_NETWORK:
        errors.append(f"unsupported_network:{network or 'empty'}")
    if network in MAINNET_NETWORKS:
        errors.append(f"mainnet_network_blocked:{network}")
    facilitator_problem = _facilitator_problem(facilitator_url)
    if facilitator_problem:
        errors.append(facilitator_problem)
    if mode == "x402_testnet" and not pay_to:
        errors.append("missing_AOX_X402_PAY_TO")
    if pay_to and not _address(pay_to):
        errors.append("invalid_AOX_X402_PAY_TO")
    if mode == "simulated" and pay_to:
        warnings.append("pay-to is configured and ignored while payment mode is simulated")

    ready = mode == "x402_testnet" and not errors
    pay_to_status = {"configured": bool(pay_to)}
    if pay_to and _address(pay_to):
        pay_to_status["address"] = pay_to
        pay_to_status["redacted"] = f"{pay_to[:6]}...{pay_to[-4:]}"
    return {
        "protocol": "x402",
        "mode": mode,
        "activeRail": "simulated_header" if mode == "simulated" else ("official_x402_testnet" if ready else "x402_testnet_config_required"),
        "ready": ready,
        "liveSettlementAllowed": False,
        "serverPrivateKeyRequired": False,
        "network": {"id": BASE_SEPOLIA_NETWORK, "label": "Base Sepolia", "testnet": True, "mainnet": False},
        "facilitator": {
            "url": "" if "@" in facilitator_url else facilitator_url,
            "defaultTestnet": facilitator_url == DEFAULT_FACILITATOR_URL,
        },
        "payTo": pay_to_status,
        "rails": _rails(),
        "acceptedAsset": "USDC",
        "errors": errors,
        "warnings": warnings,
    }


def simulated_pay_to(env=None):
    """Burn address used when a simulated decision needs a pay-to placeholder."""
    env = {} if env is None else env
    value = _pick(env, ("AOX_SIMULATED_PAY_TO", "AOE_SIMULATED_PAY_TO"), DEFAULT_SIMULATED_PAY_TO).strip()
    return value or DEFAULT_SIMULATED_PAY_TO


def ready_config(env=None):
    status = payment_status(env)
    address = status["payTo"].get("address")
    if not status["ready"] or not address:
        return None
    return {
        "mode": "x402_testnet",
        "network": BASE_SEPOLIA_NETWORK,
        "facilitatorUrl": status["facilitator"]["url"],
        "payTo": address,
    }


def create_gate(env=None):
    """Mirror ``createX402TestnetGate`` without installing payment middleware."""
    status = payment_status(env)
    config = ready_config(env)
    gate = {"status": status, "gateActive": config is not None, "liveSettlementAllowed": False}
    if config is not None:
        gate["config"] = config
    return gate


def decide_release(spec, settler=None, ledger=None):
    """Release only for a replayed OK receipt on Base Sepolia, inside the cap.

    ``spec`` uses the shared vector keys ``verdict``, ``amount``, ``network``,
    ``mode``, ``maxUsd``, and optional ``env``. ``verdict`` must be an
    ``aox-verdict-receipt@1`` object. A bare string or ``Verdict`` value is
    ``receipt_required``. The process environment is ignored. The receipt hash
    is consumed on ``ledger`` before ``settler`` runs, and a second consume is
    ``replay``. ``settled`` stays false unless ``settler`` is injected and
    returns true.
    """
    spec = {} if spec is None else spec
    env = spec.get("env") or {}
    ledger = _process_ledger() if ledger is None else ledger
    mode_text = spec.get("mode", "simulated")
    network = BASE_SEPOLIA_NETWORK if spec.get("network") is None else str(spec.get("network")).strip()
    amount = spec.get("amount")
    result = {
        "decision": "DENY",
        "reason": "verdict_not_ok",
        "verdict": None,
        "mode": "simulated",
        "network": network,
        "amount": amount if type(amount) is str else None,
        "appliedMaxUsd": None,
        "liveSettlementAllowed": False,
        "settled": False,
        "simulated": False,
    }
    if _private_key_present(env):
        return _deny(result, "private_key_refused")
    errors = []
    mode = _payment_mode("simulated" if mode_text is None else str(mode_text), errors)
    result["mode"] = mode
    result["simulated"] = mode == "simulated"
    if errors:
        return _deny(result, "unsupported_mode")
    if network in MAINNET_NETWORKS or any(str(env.get(key, "")).strip() in MAINNET_NETWORKS for key in _NETWORK_KEYS if key in env):
        blocked = network if network in MAINNET_NETWORKS else next(str(env[key]).strip() for key in _NETWORK_KEYS if key in env and str(env[key]).strip() in MAINNET_NETWORKS)
        result["network"] = blocked
        return _deny(result, "mainnet_network_blocked")
    if network != BASE_SEPOLIA_NETWORK:
        return _deny(result, "unsupported_network")
    if mode == "x402_testnet":
        status_env = dict(env)
        status_env.setdefault("AOX_PAYMENT_MODE", "x402_testnet")
        status_env.setdefault("AOX_X402_NETWORK", BASE_SEPOLIA_NETWORK)
        status = payment_status(status_env)
        if not status["ready"]:
            if "facilitator_not_allowlisted" in status["errors"]:
                return _deny(result, "facilitator_not_allowlisted")
            return _deny(result, "config_not_ready")
    verdict, receipt, failure = _read_verdict(spec.get("verdict"))
    if receipt is not None:
        result["receiptHash"] = receipt["hash"]
        result["taskId"] = receipt["task_id"]
    if failure or verdict is None or not verdict.is_success:
        result["verdict"] = None if verdict is None else verdict.value
        return _deny(result, failure or "verdict_not_ok")
    result["verdict"] = verdict.value
    try:
        cap = usd_to_micros(DEFAULT_MAX_USD if spec.get("maxUsd") is None else spec.get("maxUsd"))
    except ValueError:
        return _deny(result, "malformed_cap")
    result["appliedMaxUsd"] = _format_usd(cap)
    amount_problem = _amount_problem(amount)
    if amount_problem:
        return _deny(result, amount_problem)
    if int(amount) > cap:
        return _deny(result, "spend_cap")
    if not ledger.consume(receipt["hash"]):
        return _deny(result, "replay")
    result["decision"] = "RELEASE"
    result["reason"] = "ok"
    if settler is not None and mode == "x402_testnet":
        payload = {
            "network": network,
            "amount": amount,
            "verdict": verdict.value,
            "receiptHash": receipt["hash"],
            "taskId": receipt["task_id"],
        }
        if settler(payload) is True:
            result["settled"] = True
    return result


def usd_to_micros(value):
    """Parse a positive USD cap. Values above 5.00 clamp to 5.00."""
    text = str(value).strip()
    if not text or text[0] == "." or text.count(".") > 1:
        raise ValueError("malformed cap")
    whole, dot, frac = text.partition(".")
    if not whole.isdigit() or (dot and (not frac or len(frac) > 6 or not frac.isdigit())):
        raise ValueError("malformed cap")
    micros = int(whole) * 1_000_000 + int((frac + "000000")[:6] or "0")
    if micros <= 0:
        raise ValueError("cap must be positive")
    return min(micros, HARD_CAP_MICROS)


def within_cap(amount, max_usd):
    cap = usd_to_micros(max_usd)
    return _amount_problem(amount) is None and int(amount) <= cap


def _process_ledger():
    global _PROCESS_LEDGER
    if _PROCESS_LEDGER is None:
        _PROCESS_LEDGER = ReleaseLedger()
    return _PROCESS_LEDGER


def _read_verdict(value):
    if type(value) is not dict:
        return None, None, "receipt_required"
    try:
        replayed = replay_receipt(value)
    except ValueError:
        return None, None, "receipt_rejected"
    return Verdict(replayed["verdict"]), replayed, None


def _payment_mode(value, errors):
    normalized = value.strip().lower()
    if not normalized or normalized == "simulated":
        return "simulated"
    if normalized in ("x402_testnet", "testnet"):
        return "x402_testnet"
    errors.append(f"unsupported_payment_mode:{normalized}")
    return "simulated"


def _pick(env, keys, default):
    for key in keys:
        if key in env and env[key] is not None:
            return str(env[key])
    return default


def _private_key_present(env):
    for key, value in env.items():
        text = "" if value is None else str(value).strip()
        if not text:
            continue
        if key in _PRIVATE_KEY_KEYS or _KEY_VALUE.fullmatch(text):
            return True
    return False


def _facilitator_problem(url):
    if not url.startswith("https://"):
        return "facilitator_url_must_be_https"
    if url not in ALLOWED_FACILITATORS:
        return "facilitator_not_allowlisted"
    return None


def _address(value):
    return len(value) == 42 and value.startswith("0x") and all(ch in "0123456789abcdefABCDEF" for ch in value[2:])


def _amount_problem(amount):
    if type(amount) is not str or _AMOUNT.fullmatch(amount) is None:
        return "malformed_amount"
    if int(amount) < 1:
        return "amount_not_positive"
    return None


def _format_usd(micros):
    whole, frac = divmod(micros, 1_000_000)
    return f"{whole}.{frac:06d}"


def _deny(result, reason):
    result["decision"] = "DENY"
    result["reason"] = reason
    result["settled"] = False
    return result


def _rails():
    return [
        {
            "railId": "base-sepolia-official-x402",
            "scheme": "exact",
            "network": BASE_SEPOLIA_NETWORK,
            "runtime": "evm",
            "status": "enabled_when_configured",
            "asset": "USDC",
            "liveSettlementAllowed": False,
            "serverPrivateKeyRequired": False,
            "caveats": [
                "Requires AOX_PAYMENT_MODE=x402_testnet, AOX_X402_PAY_TO, and the allow-listed facilitator.",
                "Mainnet remains blocked.",
                "This module does not import the x402 SDK. Live settlement is the opt-in demo flag.",
            ],
        },
        {
            "railId": "solana-pay-sh-svm-candidate",
            "scheme": "exact",
            "network": SOLANA_DEVNET_NETWORK,
            "runtime": "svm",
            "status": "planned_simulated_only",
            "asset": "USDC",
            "liveSettlementAllowed": False,
            "serverPrivateKeyRequired": False,
            "caveats": ["No Solana wallet or facilitator call is enabled."],
        },
    ]
