"""Portfolio audit: list every domain, flag expiring ones (read-only).

Walks the paginated domain list and prints an expiry-sorted report with
autorenew, privacy and lifecycle status per domain.

Usage:
    python examples/portfolio.py
    python examples/portfolio.py --expiring-within 60 --page-size 50
"""

from __future__ import annotations

import argparse
import datetime
import sys

sys.path.insert(0, "src")

from _common import print_table, require_client  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page-size", type=int, default=100, help="Domains per page (1-100).")
    parser.add_argument(
        "--expiring-within",
        type=int,
        default=30,
        help="Flag domains expiring within this many days.",
    )
    parser.add_argument("--details", action="store_true", help="Call get_info per domain (slower).")
    args = parser.parse_args(argv)

    today = datetime.date.today()
    rows: list[list[str]] = []
    expiring = 0
    with require_client() as sp:
        page = 1
        while True:
            domains = sp.domains.list(page=page, page_size=args.page_size)
            if not domains:
                break
            for domain in domains:
                info = sp.domains.get_info(domain.name) if args.details else domain
                expiry = info.expiration_date.date().isoformat() if info.expiration_date else "?"
                days = (info.expiration_date.date() - today).days if info.expiration_date else None
                flag = "EXPIRING" if days is not None and days <= args.expiring_within else ""
                expiring += bool(flag)
                rows.append(
                    [
                        info.name,
                        expiry,
                        "auto" if info.auto_renew else "manual",
                        info.privacy.level or "-",
                        info.lifecycle_status or "-",
                        flag,
                    ]
                )
            if len(domains) < args.page_size:
                break
            page += 1

    rows.sort(key=lambda r: r[1])
    print_table(rows, ["domain", "expires", "renew", "privacy", "status", "flag"])
    print(f"\n{len(rows)} domain(s), {expiring} expiring within {args.expiring_within}d")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
