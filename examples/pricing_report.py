"""Storefront pricing report (no API key): rank TLDs, export a price table.

Fetches register/renew/transfer quotes and prints the cheapest extensions,
optionally as CSV/Markdown for feeding catalog jobs. Transfer quotes come
from the transfer=1 purchase leg (see pricing module docs).

Usage:
    python examples/pricing_report.py --tlds com,net,org,io,ai
    python examples/pricing_report.py --tlds-file tlds.txt --format csv > prices.csv
    python examples/pricing_report.py --tlds com --fetcher direct --format markdown
"""

from __future__ import annotations

import argparse
import csv
import sys

sys.path.insert(0, "src")

from _common import print_table  # noqa: E402

from spaceship import StorefrontPricing, TldPrice  # noqa: E402


def _load_tlds(args: argparse.Namespace) -> list[str]:
    tlds: list[str] = []
    if args.tlds:
        tlds.extend(t.strip() for t in args.tlds.split(",") if t.strip())
    if args.tlds_file:
        with open(args.tlds_file, encoding="utf-8") as fh:
            tlds.extend(line.strip() for line in fh if line.strip())
    if not tlds:
        raise SystemExit("give --tlds or --tlds-file.")
    return tlds


def _rows(prices: list[TldPrice]) -> list[list[str]]:
    return [
        [
            f".{p.tld}",
            str(p.register or "-"),
            str(p.renew or "-"),
            str(p.transfer or "-"),
            p.currency,
        ]
        for p in sorted(prices, key=lambda p: (p.register is None, p.register or 0))
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tlds", help="Comma-separated TLDs.")
    parser.add_argument("--tlds-file", help="File with one TLD per line.")
    parser.add_argument("--fetcher", default=None, help="direct, playwright, scraping_api.")
    parser.add_argument("--top", type=int, default=0, help="Show only the N cheapest by register price.")
    parser.add_argument("--no-transfer", action="store_true", help="Skip the transfer pass.")
    parser.add_argument("--format", choices=["table", "csv", "markdown"], default="table")
    args = parser.parse_args(argv)

    pricing = StorefrontPricing.from_env(**({"fetcher": args.fetcher} if args.fetcher else {}))
    prices = pricing.fetch(_load_tlds(args), include_transfer=not args.no_transfer)
    rows = _rows(prices)[: args.top or None]
    headers = ["tld", "register", "renew", "transfer", "currency"]
    if args.format == "csv":
        writer = csv.writer(sys.stdout)
        writer.writerow(headers)
        writer.writerows(rows)
    elif args.format == "markdown":
        print("| " + " | ".join(headers) + " |")
        print("|" + "|".join(["---"] * len(headers)) + "|")
        for row in rows:
            print("| " + " | ".join(row) + " |")
    else:
        print_table(rows, headers)
        print(f"\n{len(rows)} TLD(s) quoted in {prices[0].currency if prices else '?'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
