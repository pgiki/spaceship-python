"""List DNS records for a domain on Spaceship nameservers."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, "src")

from spaceship import Spaceship


def main(domain: str = "example.com") -> None:
    if not os.environ.get("SPACESHIP_API_KEY"):
        print("Set SPACESHIP_API_KEY and SPACESHIP_API_SECRET first.")
        raise SystemExit(1)
    sp = Spaceship()
    for record in sp.dns.list(domain):
        print(f"{record.type:6} {record.fqdn(domain):40} {record.address or ''}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "example.com")
