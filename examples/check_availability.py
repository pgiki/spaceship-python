"""Bulk domain availability check (free endpoint, no charges).

Shows the key gotcha: only *premium* domains come back with a price
(``premiumPricing``); standard domains return an empty price list even when
available, so callers must handle priceless results.

Usage:
    python examples/check_availability.py example.com my-new-project.dev
    python examples/check_availability.py --file candidates.txt
    python examples/check_availability.py --single example.com
"""

from __future__ import annotations

import argparse
import sys

sys.path.insert(0, "src")

from _common import print_table, require_client  # noqa: E402

from spaceship.idn import from_punycode, to_punycode  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("domains", nargs="*", help="Domains to check.")
    parser.add_argument("--file", help="File with one domain per line.")
    parser.add_argument(
        "--single",
        action="store_true",
        help="Use GET /domains/{domain}/available per domain instead of the batch call.",
    )
    args = parser.parse_args(argv)

    wanted: list[str] = list(args.domains)
    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            wanted.extend(line.strip() for line in fh if line.strip())
    if not wanted:
        parser.error("give at least one domain or --file.")

    with require_client() as sp:
        if args.single:
            checks = [sp.domains.check_single(to_punycode(d)) for d in wanted]
        else:
            checks = sp.domains.check(*[to_punycode(d) for d in wanted])

    rows, available = [], 0
    for check in checks:
        price = f"${check.price} {check.currency}" if check.price is not None else "n/a (standard)"
        mark = "available" if check.available else check.result or "taken"
        available += check.available
        rows.append([from_punycode(check.domain), mark, "premium" if check.premium else "-", price])
    print_table(rows, ["domain", "status", "tier", "price"])
    print(f"\n{available}/{len(checks)} available")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
