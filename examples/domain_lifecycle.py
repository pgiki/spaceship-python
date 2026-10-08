"""Domain lifecycle: register / renew / transfer-in / restore / settings.

⚠️  CHARGES MONEY: register, renew, transfer and restore bill the account's
    default payment method. Every charging subcommand requires --yes AND an
    interactive YES confirmation. The `info` and `settings --show` paths are
    read-only.

Async pattern: pass --no-wait to get the pending AsyncOperation immediately
and poll it yourself with operations.wait_for() instead of blocking.

Usage:
    python examples/domain_lifecycle.py info example.com
    python examples/domain_lifecycle.py register example.com --contact-id CID --yes
    python examples/domain_lifecycle.py register example.com --contact-id CID --no-wait --yes
    python examples/domain_lifecycle.py renew example.com --years 2 --yes
    python examples/domain_lifecycle.py transfer-in example.com --contact-id CID --yes
    python examples/domain_lifecycle.py settings example.com --autorenew on --lock
"""

from __future__ import annotations

import argparse
import sys

sys.path.insert(0, "src")

from _common import confirm, require_client  # noqa: E402

from spaceship import AsyncOperation  # noqa: E402


def _add_contact_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--contact-id",
        required=True,
        help="Contact ID for registrant/admin/tech/billing (see contacts.py).",
    )


def _add_wait_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--years", type=int, default=1, help="Registration years (1-10).")
    parser.add_argument("--no-wait", action="store_true", help="Return the pending operation.")
    parser.add_argument("--yes", action="store_true", help="Required to bill the account.")


def _report(result: object, verb: str) -> int:
    if isinstance(result, AsyncOperation):
        print(f"{verb} accepted, operation {result.id} status={result.status}")
        print("Poll with: sp.operations.wait_for(op_id)")
    else:
        print(f"{verb} finished: {getattr(result, 'name', result)}")
    return 0


def cmd_info(sp, args: argparse.Namespace) -> int:
    info = sp.domains.get_info(args.domain)
    print(f"name:        {info.name} ({info.unicode_name})")
    print(f"premium:     {info.is_premium}")
    print(f"registered:  {info.registration_date}")
    print(f"expires:     {info.expiration_date}")
    print(f"auto-renew:  {info.auto_renew}")
    print(f"lifecycle:   {info.lifecycle_status} / {info.verification_status}")
    print(f"privacy:     {info.privacy.level} (contact form: {info.privacy.contact_form})")
    print(f"nameservers: {info.nameservers.provider} {', '.join(info.nameservers.hosts)}")
    print(f"contacts:    registrant={info.contacts.registrant} admin={info.contacts.admin}")
    try:
        print(f"transfer:    {sp.domains.transfer_info(args.domain)}")
    except Exception as exc:  # transfer info is not available for every domain
        print(f"transfer:    n/a ({exc})")
    return 0


def cmd_register(sp, args: argparse.Namespace) -> int:
    if not args.yes or not confirm(f"register {args.domain} for {args.years} year(s)"):
        print("Aborted (pass --yes and type YES).")
        return 2
    return _report(
        sp.domains.register(
            args.domain,
            contact={
                "registrant": args.contact_id,
                "admin": args.contact_id,
                "tech": args.contact_id,
                "billing": args.contact_id,
            },
            years=args.years,
            auto_renew=args.auto_renew,
            wait=not args.no_wait,
        ),
        "register",
    )


def cmd_renew(sp, args: argparse.Namespace) -> int:
    if not args.yes or not confirm(f"renew {args.domain} for {args.years} year(s)"):
        print("Aborted (pass --yes and type YES).")
        return 2
    return _report(sp.domains.renew(args.domain, years=args.years, wait=not args.no_wait), "renew")


def cmd_transfer(sp, args: argparse.Namespace) -> int:
    if not args.yes or not confirm(f"transfer {args.domain} in (charged like a renewal)"):
        print("Aborted (pass --yes and type YES).")
        return 2
    return _report(
        sp.domains.transfer(
            args.domain,
            contact={
                "registrant": args.contact_id,
                "admin": args.contact_id,
                "tech": args.contact_id,
                "billing": args.contact_id,
            },
            auth_code=args.auth_code,
            wait=not args.no_wait,
        ),
        "transfer",
    )


def cmd_restore(sp, args: argparse.Namespace) -> int:
    if not args.yes or not confirm(f"restore {args.domain} from redemption (restoration fee applies)"):
        print("Aborted (pass --yes and type YES).")
        return 2
    return _report(sp.domains.restore(args.domain, wait=not args.no_wait), "restore")


def cmd_settings(sp, args: argparse.Namespace) -> int:
    if args.show:
        return cmd_info(sp, args)
    if args.autorenew:
        print("autorenew:", sp.domains.set_autorenew(args.domain, args.autorenew == "on"))
    if args.lock:
        print("locked:", sp.domains.set_lock(args.domain, args.lock == "on"))
    if args.nameservers is not None:
        hosts = [] if args.nameservers == ["basic"] else args.nameservers
        sp.domains.set_nameservers(args.domain, hosts)
        print("nameservers:", "basic" if not hosts else ", ".join(hosts))
    if args.privacy:
        sp.domains.set_privacy(args.privacy, args.domain)
        print("privacy:", args.privacy)
    if args.contact_form is not None:
        sp.domains.set_email_protection(args.domain, contact_form=args.contact_form)
        print("contact form:", args.contact_form)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("info", help="Show domain details (read-only).")
    p.add_argument("domain")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("register", help="Register a domain (CHARGED).")
    p.add_argument("domain")
    p.add_argument("--auto-renew", action="store_true")
    _add_contact_arg(p)
    _add_wait_args(p)
    p.set_defaults(func=cmd_register)

    p = sub.add_parser("renew", help="Renew a domain (CHARGED).")
    p.add_argument("domain")
    _add_wait_args(p)
    p.set_defaults(func=cmd_renew)

    p = sub.add_parser("transfer-in", help="Transfer a domain in (CHARGED).")
    p.add_argument("domain")
    p.add_argument("--auth-code", default=None, help="EPP auth code from the losing registrar.")
    _add_contact_arg(p)
    p.add_argument("--no-wait", action="store_true")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_transfer)

    p = sub.add_parser("restore", help="Restore from redemption (CHARGED).")
    p.add_argument("domain")
    p.add_argument("--no-wait", action="store_true")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_restore)

    p = sub.add_parser("settings", help="Tweak autorenew/lock/nameservers/privacy.")
    p.add_argument("domain")
    p.add_argument("--show", action="store_true", help="Read-only view.")
    p.add_argument("--autorenew", choices=["on", "off"])
    p.add_argument("--lock", choices=["on", "off"])
    p.add_argument("--nameservers", nargs="*", help="Hosts, or 'basic' for Spaceship DNS.")
    p.add_argument("--privacy", choices=["public", "high"])
    p.add_argument("--contact-form", action=argparse.BooleanOptionalAction)
    p.set_defaults(func=cmd_settings)

    args = parser.parse_args(argv)
    with require_client() as sp:
        return args.func(sp, args)


if __name__ == "__main__":
    raise SystemExit(main())
