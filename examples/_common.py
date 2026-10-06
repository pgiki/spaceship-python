"""Shared helpers for the runnable examples (not standalone).

Every script does ``sys.path.insert(0, "src")`` so it runs from a checkout
without installing the package first.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, "src")

from spaceship import Spaceship  # noqa: E402


def require_client() -> Spaceship:
    """Return an authenticated client or exit with setup instructions."""
    if not os.environ.get("SPACESHIP_API_KEY") or not os.environ.get("SPACESHIP_API_SECRET"):
        print("Set SPACESHIP_API_KEY and SPACESHIP_API_SECRET first.")
        print("Create them at https://www.spaceship.com/application/api-manager/")
        raise SystemExit(2)
    return Spaceship()


def confirm(action: str) -> bool:
    """Ask the user to type YES before a charging/mutating operation."""
    answer = input(f'Type YES to {action}: ').strip()
    return answer == "YES"


def print_table(rows: list[list[str]], headers: list[str]) -> None:
    """Print a minimal aligned table (no third-party dependencies)."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*headers))
    print(fmt.format(*["-" * w for w in widths]))
    for row in rows:
        print(fmt.format(*row))
