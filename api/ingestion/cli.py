"""Operator commands for terms and imports.

Run as `python -m ingestion.cli --help`. Exit codes: 0 on success, 2 on a
usage, validation, or lookup error.
"""

import argparse
import sys
from collections.abc import Callable, Sequence
from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.models import Term, TermStatus
from ingestion.persist import taxonomy_term_id

EXIT_OK = 0
EXIT_USAGE = 2

_STATUS_CHOICES = [status.value for status in TermStatus]


class CliError(Exception):
    """A user-facing error: printed without a traceback, exits EXIT_USAGE."""


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"invalid date {value!r}: expected YYYY-MM-DD"
        ) from None


def _timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise argparse.ArgumentTypeError(f"unknown timezone {value!r}") from None
    return value


def _source_url(value: str) -> str:
    try:
        taxonomy_term_id(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"invalid source URL {value!r}: expected "
            "https://classes.berkeley.edu/taxonomy/term/{id}"
        ) from None
    return value


def _resolve_term(db: Session, ref: str) -> Term:
    """Finds a term by numeric id, falling back to an exact name match."""
    term = db.get(Term, int(ref)) if ref.isdigit() else None
    if term is None:
        term = db.scalars(select(Term).where(Term.name == ref)).one_or_none()
    if term is None:
        raise CliError(f"no term matching {ref!r}")
    return term


def _term_create(args: argparse.Namespace, db: Session) -> int:
    if args.start >= args.end:
        raise CliError("--start must be before --end")
    duplicate_error = f"a term named {args.name!r} already exists"
    existing = db.scalars(select(Term).where(Term.name == args.name)).one_or_none()
    if existing is not None:
        raise CliError(f"{duplicate_error} (id {existing.term_id})")

    term = Term(
        name=args.name,
        start_date=args.start,
        end_date=args.end,
        source_url=args.source_url,
        status=TermStatus(args.status),
    )
    # Left unset without --timezone so the model's default applies.
    if args.timezone is not None:
        term.timezone = args.timezone
    db.add(term)
    try:
        db.commit()
    except IntegrityError:
        # Another process created the same name since the check above.
        db.rollback()
        raise CliError(duplicate_error) from None

    print(
        f"Created term {term.term_id}: {term.name} "
        f"({term.start_date} to {term.end_date}, "
        f"taxonomy term {taxonomy_term_id(term.source_url)}, {term.status.value})"
    )
    return EXIT_OK


def _term_list(args: argparse.Namespace, db: Session) -> int:
    terms = db.scalars(select(Term).order_by(Term.start_date, Term.term_id)).all()
    if not terms:
        print("No terms.")
        return EXIT_OK

    rows = [("ID", "NAME", "START", "END", "STATUS", "SOURCE URL")] + [
        (
            str(term.term_id),
            term.name,
            str(term.start_date),
            str(term.end_date),
            term.status.value,
            term.source_url or "",
        )
        for term in terms
    ]
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]) - 1)]
    for row in rows:
        cells = [cell.ljust(width) for cell, width in zip(row, widths)] + [row[-1]]
        print("  ".join(cells).rstrip())
    return EXIT_OK


def _term_set_status(args: argparse.Namespace, db: Session) -> int:
    term = _resolve_term(db, args.term)
    new_status = TermStatus(args.status)
    if term.status == new_status:
        print(f"Term {term.term_id} ({term.name}): already {new_status.value}")
        return EXIT_OK

    old_status = term.status
    term.status = new_status
    db.commit()
    print(
        f"Term {term.term_id} ({term.name}): "
        f"{old_status.value} -> {new_status.value}"
    )
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ingestion.cli",
        description="Manage terms and schedule imports.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    term = commands.add_parser("term", help="create, list, or archive terms")
    term_commands = term.add_subparsers(dest="term_command", required=True)

    create = term_commands.add_parser("create", help="create a term")
    create.add_argument("--name", required=True, help='e.g. "Fall 2026"')
    create.add_argument("--start", required=True, type=_iso_date, help="YYYY-MM-DD")
    create.add_argument("--end", required=True, type=_iso_date, help="YYYY-MM-DD")
    create.add_argument(
        "--source-url",
        required=True,
        type=_source_url,
        help="the term's https://classes.berkeley.edu/taxonomy/term/{id} page",
    )
    create.add_argument(
        "--timezone",
        type=_timezone,
        help="IANA timezone (default: America/Los_Angeles)",
    )
    create.add_argument("--status", choices=_STATUS_CHOICES, default="active")
    create.set_defaults(handler=_term_create)

    list_ = term_commands.add_parser("list", help="list terms by start date")
    list_.set_defaults(handler=_term_list)

    set_status = term_commands.add_parser(
        "set-status", help="mark a term active or archived"
    )
    set_status.add_argument("term", help="term id or exact name")
    set_status.add_argument("status", choices=_STATUS_CHOICES)
    set_status.set_defaults(handler=_term_set_status)

    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    db_factory: Callable[[], Session] = SessionLocal,
) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse exits on --help (0) and on usage errors (2); return the
        # code instead so callers and tests always get an int back.
        return exc.code if isinstance(exc.code, int) else EXIT_USAGE

    try:
        with db_factory() as db:
            return args.handler(args, db)
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
