"""Contact lifecycle: create, read, reuse and extend registrant contacts.

Contact IDs are what domain operations (register/transfer) actually take,
so create yours once and reuse them. `ensure()` verifies an existing ID or
saves new details when given none.

Usage:
    python examples/contacts.py create --email you@example.com --first Ada --last Lovelace \
        --city Dar --country TZ --phone +255700000000
    python examples/contacts.py read CONTACT_ID
    python examples/contacts.py ensure --contact-id CONTACT_ID
    python examples/contacts.py attrs CONTACT_ID --attr taxNumber=123 --attr legalType=individual
"""

from __future__ import annotations

import argparse
import sys

sys.path.insert(0, "src")

from _common import require_client  # noqa: E402

from spaceship import Contact  # noqa: E402


def cmd_create(sp, args: argparse.Namespace) -> int:
    contact = Contact(
        first_name=args.first,
        last_name=args.last,
        organization=args.org or None,
        email=args.email,
        address1=args.address,
        city=args.city,
        country=args.country,
        phone=args.phone,
        postal_code=args.postcode,
    )
    contact_id = sp.contacts.save(contact)
    print(f"created contact {contact_id}")
    print("Reuse it: --contact-id", contact_id)
    return 0


def cmd_read(sp, args: argparse.Namespace) -> int:
    contact = sp.contacts.read(args.contact_id)
    print(f"id:      {contact.id}")
    print(f"name:    {contact.first_name} {contact.last_name} ({contact.organization})")
    print(f"email:   {contact.email}")
    print(f"address: {contact.address1}, {contact.city} {contact.postal_code} {contact.country}")
    print(f"phone:   {contact.phone}")
    return 0


def cmd_ensure(sp, args: argparse.Namespace) -> int:
    contact_id = sp.contacts.ensure({"contact_id": args.contact_id} if args.contact_id else {})
    print(f"usable contact id: {contact_id or '(pass --contact-id or create one first)'}")
    return 0


def cmd_attrs(sp, args: argparse.Namespace) -> int:
    if args.attr:
        attributes = dict(pair.split("=", 1) for pair in args.attr)
        sp.contacts.save_attributes({"contactId": args.contact_id, **attributes})
        print("saved:", attributes)
    print("current:", sp.contacts.get_attributes(args.contact_id))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("create", help="Create a contact; prints its ID.")
    p.add_argument("--email", required=True)
    p.add_argument("--first", required=True)
    p.add_argument("--last", required=True)
    p.add_argument("--org", default="")
    p.add_argument("--address", default="Sam Nujoma Road")
    p.add_argument("--city", default="Dar es Salaam")
    p.add_argument("--country", default="TZ", help="ISO alpha-2.")
    p.add_argument("--phone", default="")
    p.add_argument("--postcode", default="00000")
    p.set_defaults(func=cmd_create)

    p = sub.add_parser("read", help="Show a contact by ID.")
    p.add_argument("contact_id")
    p.set_defaults(func=cmd_read)

    p = sub.add_parser("ensure", help="Verify an ID (or save when empty).")
    p.add_argument("--contact-id", default="")
    p.set_defaults(func=cmd_ensure)

    p = sub.add_parser("attrs", help="Save/read TLD-specific attributes.")
    p.add_argument("contact_id")
    p.add_argument("--attr", action="append", default=[], help="KEY=VALUE (repeatable).")
    p.set_defaults(func=cmd_attrs)

    args = parser.parse_args(argv)
    with require_client() as sp:
        return args.func(sp, args)


if __name__ == "__main__":
    raise SystemExit(main())
