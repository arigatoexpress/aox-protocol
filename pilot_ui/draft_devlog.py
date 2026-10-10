"""Render a local, unpublished devlog draft from a replay-validated synthetic receipt."""
import argparse
import json
from pathlib import Path

from pilot_ui.app import MAX_BODY, inspect_receipt


def draft(receipt):
    view = inspect_receipt(receipt)
    request, checkpoint = view['request'], view['checkpoint']
    status = request['status']
    return (f'DRAFT ONLY — SYNTHETIC DEMO — NOT PUBLISHED\n\n'
            f'AOX local task lab: a text.upper@1 fixture ended with status {status}. '
            f'The supplied receipt replayed {checkpoint["event_count"]} events with valid '
            f'hashes and transitions. This checks internal consistency, not authorship '
            f'or real-world execution.\n\n'
            f'Evidence: the exact input receipt supplied to this command; '
            f'format aox-pilot-receipt@1, event count {checkpoint["event_count"]}, '
            f'final SHA-256 {checkpoint["final_hash"]}.\n\n'
            f'This is a synthetic offline demonstration, not a live marketplace or real-agent pilot. '
            f'It provides no verified adoption, demand or revenue evidence. '
            f'Fixture units have no monetary or token conversion.\n\n'
            f'Owner review required before any external use: attach the exact receipt, '
            f'check this reference against it, and retain the synthetic label. '
            f'No posting or scheduling has occurred.\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipt', type=Path)
    args = parser.parse_args()
    try:
        with args.receipt.open('rb') as source:
            raw = source.read(MAX_BODY + 1)
        if len(raw) > MAX_BODY:
            raise ValueError('receipt exceeds 256 KiB')
        result = draft(json.loads(raw))
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError, OverflowError):
        parser.exit(2, 'Receipt could not be validated; no draft generated.\n')
    print(result, end='')


if __name__ == '__main__':
    main()
