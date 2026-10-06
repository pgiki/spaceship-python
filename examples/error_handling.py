"""Error handling tour (fully offline — safe to run anywhere).

Demonstrates the SDK's error shapes without touching the network:
PricingError from a malformed BFF payload, NotSupportedError for endpoints
with no Spaceship equivalent, SpaceshipError construction from API bodies,
plus IDN edge cases and the documented rate limits.

Usage:
    python examples/error_handling.py
"""

from __future__ import annotations

import sys

sys.path.insert(0, "src")

from spaceship import (  # noqa: E402
    AsyncOperationError,
    NotSupportedError,
    PricingError,
    Spaceship,
    SpaceshipError,
    parse_bff_response,
)
from spaceship.idn import from_punycode, to_punycode  # noqa: E402


def main() -> int:
    # 1. Pricing payload errors carry a machine-readable code.
    try:
        parse_bff_response({"nope": 1}, transfer_mode=False)
    except PricingError as exc:
        print(f"PricingError: code={exc.code} message={exc.message}")

    # 2. Unsupported endpoints fail fast with an alternative hint (no request sent).
    try:
        Spaceship(api_key="x", api_secret="y").domains.get_tld_list()
    except NotSupportedError as exc:
        print(f"NotSupportedError: {exc} (alternative: {exc.alternative!r})")

    # 3. API problem bodies parse into status/code/details.
    err = SpaceshipError.from_response(422, {"detail": "Postal code is invalid.", "code": "E100"})
    print(f"SpaceshipError: {err} | details={err.details}")

    # 4. Failed async operations keep the operation id for support tickets.
    print(f"AsyncOperationError: {AsyncOperationError('abc123', {'reason': 'registry refused'})}")

    # 5. IDN helpers are total: garbage in, best-effort out.
    print(f"IDN: {to_punycode('müller.de')} / {from_punycode('xn--mller-kva.de')}")

    print(
        "\nRate limits (from docs): availability 30 req/30s (20 domains/call), "
        "domain info 5 req/domain/300s, domain list 300 req/300s."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
