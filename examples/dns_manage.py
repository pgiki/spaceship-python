"""DNS zone management (domains on Spaceship nameservers).

The API is whole-zone oriented: `set()` REPLACES the zone, and the
single-record helpers are read-modify-write over it. Mutating subcommands
are dry-run by default — pass --apply to write.

Usage:
    python examples/dns_manage.py example.com list
    python examples/dns_manage.py example.com add --type TXT --name @ --address "v=spf1 -all"
    python examples/dns_manage.py example.com set-a --ip 1.2.3.4 --apply
    python examples/dns_manage.py example.com delete --name old --type A --apply
"""

from __future__ import annotations

import argparse
import sys

sys.path.insert(0, "src")

from _common import confirm, print_table, require_client  # noqa: E402

from spaceship import DNSRecord  # noqa: E402


def _show(records: list[DNSRecord], zone: str) -> None:
    print_table(
        [[r.type, r.fqdn(zone), r.address or "", str(r.ttl or "")] for r in records],
        ["type", "name", "address", "ttl"],
    )


def cmd_list(sp, args: argparse.Namespace) -> int:
    _show(sp.dns.list(args.zone), args.zone)
    return 0


def cmd_add(sp, args: argparse.Namespace) -> int:
    planned = DNSRecord(type=args.type.upper(), name=args.name, address=args.address, ttl=args.ttl)
    if not args.apply:
        print(f"dry run — would append: {planned.type} {planned.fqdn(args.zone)} {planned.address}")
        print("Re-run with --apply to write.")
        return 0
    if not confirm(f"add {planned.type} {planned.fqdn(args.zone)}"):
        return 2
    added = sp.dns.add(args.zone, planned)
    print(f"added: {added.type} {added.fqdn(args.zone)}")
    return 0


def cmd_set_a(sp, args: argparse.Namespace) -> int:
    names = ["@", "www"] if not args.no_www else ["@"]
    if args.wildcard:
        names.append("*")
    if not args.apply:
        print(f"dry run — would point {', '.join(names)}.{args.zone} at {args.ip}")
        print("Existing A records on those names would be replaced. Re-run with --apply.")
        return 0
    if not confirm(f"point {args.zone} at {args.ip}"):
        return 2
    records = sp.dns.set_a_records(args.zone, args.zone, args.ip,
                                   include_www=not args.no_www,
                                   include_wildcard=args.wildcard, ttl=args.ttl)
    _show(records, args.zone)
    return 0


def cmd_delete(sp, args: argparse.Namespace) -> int:
    current = sp.dns.list(args.zone)
    doomed = [
        r for r in current
        if (args.name is None or r.name.lower() == args.name.lower().lstrip("."))
        and (args.type is None or r.type.upper() == args.type.upper())
        and (args.value is None or (r.address or "") == args.value)
    ]
    if args.name is None and args.type is None and args.value is None:
        print("Refusing to wipe the zone: pass at least one of --name/--type/--value.")
        return 2
    if not doomed:
        print("Nothing matches.")
        return 0
    _show(doomed, args.zone)
    if not args.apply:
        print(f"dry run — would delete {len(doomed)} record(s). Re-run with --apply.")
        return 0
    if not confirm(f"delete {len(doomed)} record(s) from {args.zone}"):
        return 2
    if args.exact:
        sp.dns.delete_exact(args.zone, doomed)
    else:
        sp.dns.delete(args.zone, name=args.name, record_type=args.type, value=args.value)
    print("deleted.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zone", help="Zone apex, e.g. example.com.")
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry run).")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list", help="Show all records.")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("add", help="Append one record.")
    p.add_argument("--type", required=True)
    p.add_argument("--name", required=True, help="'@' for apex, else relative name.")
    p.add_argument("--address", required=True)
    p.add_argument("--ttl", type=int, default=None)
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("set-a", help="Point @ (+www) at an IP.")
    p.add_argument("--ip", required=True)
    p.add_argument("--no-www", action="store_true")
    p.add_argument("--wildcard", action="store_true")
    p.add_argument("--ttl", type=int, default=None)
    p.set_defaults(func=cmd_set_a)

    p = sub.add_parser("delete", help="Delete matching records.")
    p.add_argument("--name")
    p.add_argument("--type")
    p.add_argument("--value", help="Match on address/content.")
    p.add_argument("--exact", action="store_true", help="Use the exact-delete endpoint.")
    p.set_defaults(func=cmd_delete)

    args = parser.parse_args(argv)
    with require_client() as sp:
        return args.func(sp, args)


if __name__ == "__main__":
    raise SystemExit(main())
