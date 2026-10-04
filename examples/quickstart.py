"""Check domain availability (free endpoint, no charges)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, "src")

from spaceship import Spaceship


def main() -> None:
    if not os.environ.get("SPACESHIP_API_KEY"):
        print("Set SPACESHIP_API_KEY and SPACESHIP_API_SECRET first.")
        raise SystemExit(1)
    sp = Spaceship()
    for check in sp.domains.check("example.com", "my-new-project.dev"):
        price = f"${check.price} {check.currency}" if check.price is not None else "n/a"
        mark = "available" if check.available else "taken"
        print(f"{check.domain}: {mark} ({price})")


if __name__ == "__main__":
    main()
