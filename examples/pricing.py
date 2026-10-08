"""Fetch bulk TLD prices from the Spaceship storefront (no API key needed)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, "src")

from spaceship import StorefrontPricing


def main() -> None:
    fetcher = os.environ.get("SPACESHIP_PRICING_FETCHER", "playwright")
    pricing = StorefrontPricing.from_env(fetcher=fetcher)
    for quote in pricing.fetch(["com", "org", "ai"]):
        print(
            f".{quote.tld}: register {quote.register} renew {quote.renew} transfer {quote.transfer} ({quote.currency})"
        )


if __name__ == "__main__":
    main()
