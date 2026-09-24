"""Operator commands for terms and imports.

Run as `python -m ingestion.cli --help`. Exit codes:

  0  success
  1  import failed or aborted (recorded as a FAILED ImportRun)
  2  usage, validation, or lookup error - nothing was run
  3  import completed, but some sections failed to fetch/parse, so
     stale-meeting cleanup was skipped
"""

import argparse
import logging
import sys
import time
from collections.abc import Callable, Sequence
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models.models import ImportRun, ImportStatus, Term, TermStatus
from ingestion.fetch import SectionSession, build_session
from ingestion.persist import run_import, taxonomy_term_id

logger = logging.getLogger("ingestion.cli")

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_PARTIAL = 3

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


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        number = 0
    if number < 1:
        raise argparse.ArgumentTypeError(f"expected a positive integer, got {value!r}")
    return number


def _non_negative_float(value: str) -> float:
    try:
        number = float(value)
    except ValueError:
        number = -1.0
    if not number >= 0:
        raise argparse.ArgumentTypeError(f"expected a number >= 0, got {value!r}")
    return number


def _fraction(value: str) -> float:
    try:
        number = float(value)
    except ValueError:
        number = -1.0
    if not 0 <= number <= 1:
        raise argparse.ArgumentTypeError(
            f"expected a number from 0 to 1, got {value!r}"
        )
    return number


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


def _failed_run_label(db: Session, term_id: int, started_at: datetime) -> str:
    """Names the FAILED ImportRun this invocation recorded, if it can.

    Best-effort: if the failure was the database itself, run_import may not
    have been able to record one, and looking it up can fail the same way.
    """
    try:
        db.rollback()
        failed_run = db.scalars(
            select(ImportRun)
            .where(
                ImportRun.term_id == term_id,
                ImportRun.status == ImportStatus.FAILED,
                ImportRun.started_at >= started_at,
            )
            .order_by(ImportRun.import_id.desc())
            .limit(1)
        ).one_or_none()
    except Exception:
        logger.debug("couldn't look up the failed ImportRun", exc_info=True)
        return "import (not recorded)"
    return f"import {failed_run.import_id}" if failed_run else "import (not recorded)"


def _import_run(
    args: argparse.Namespace,
    db: Session,
    session_factory: Callable[[], SectionSession],
) -> int:
    term = _resolve_term(db, args.term)
    if term.status == TermStatus.ARCHIVED and not args.allow_archived:
        raise CliError(
            f"term {term.term_id} ({term.name}) is archived - pass "
            "--allow-archived to import it anyway"
        )
    try:
        taxonomy_term_id(term.source_url)
    except ValueError as exc:
        raise CliError(
            f"term {term.term_id} ({term.name}) can't be imported: {exc}"
        ) from None
    term_id, term_name = term.term_id, term.name

    rate_limit_seconds = (
        args.rate_limit_seconds
        if args.rate_limit_seconds is not None
        else get_settings().scraper_rate_limit_seconds
    )
    logger.info("importing term %s (%s) from %s", term_id, term_name, term.source_url)
    started = time.monotonic()
    started_at = datetime.now(timezone.utc)
    session = session_factory()
    try:
        import_run = run_import(
            db,
            session,
            term_id,
            rate_limit_seconds=rate_limit_seconds,
            max_pages=args.max_pages,
            parser_version=args.parser_version,
            max_retire_fraction=args.max_retire_fraction,
        )
    except Exception as exc:
        # run_import has already logged the traceback, recorded a FAILED
        # ImportRun, and rolled back this run's changes - just summarize.
        run_label = _failed_run_label(db, term_id, started_at)
        logger.error(
            "%s for term %s (%s) FAILED after %.0fs: %s: %s",
            run_label,
            term_id,
            term_name,
            time.monotonic() - started,
            type(exc).__name__,
            exc,
        )
        return EXIT_FAILED
    finally:
        close = getattr(session, "close", None)
        if close is not None:
            close()

    summary = (
        f"import {import_run.import_id} for term {term_id} ({term_name}) "
        f"{import_run.status.value.upper()} in {time.monotonic() - started:.0f}s: "
        f"{import_run.records_read} read, {import_run.records_imported} imported, "
        f"{import_run.records_rejected} rejected, "
        f"{import_run.records_failed} failed"
    )
    if import_run.records_failed:
        logger.warning(
            "%s - stale-meeting cleanup was skipped because some sections "
            "failed; re-run once the source recovers",
            summary,
        )
        return EXIT_PARTIAL
    logger.info("%s", summary)
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

    import_ = commands.add_parser("import", help="import a term's schedule")
    import_commands = import_.add_subparsers(dest="import_command", required=True)

    run = import_commands.add_parser(
        "run", help="scrape the term's sections and persist them"
    )
    run.add_argument("term", help="term id or exact name")
    run.add_argument(
        "--max-pages",
        type=_positive_int,
        default=5000,
        help="taxonomy listing pages to read before failing (default: 5000)",
    )
    run.add_argument(
        "--max-retire-fraction",
        type=_fraction,
        default=0.5,
        help="abort if more than this fraction of the term's sections would be "
        "removed (default: 0.5; 1.0 allows any change)",
    )
    run.add_argument(
        "--rate-limit-seconds",
        type=_non_negative_float,
        help="delay between requests (default: SCRAPER_RATE_LIMIT_SECONDS)",
    )
    run.add_argument("--parser-version", help="recorded on the ImportRun for debugging")
    run.add_argument(
        "--allow-archived",
        action="store_true",
        help="import a term even if it's archived",
    )
    run.set_defaults(handler=_import_run, needs_scraper=True)

    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    db_factory: Callable[[], Session] = SessionLocal,
    session_factory: Callable[[], SectionSession] = build_session,
) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse exits on --help (0) and on usage errors (2); return the
        # code instead so callers and tests always get an int back.
        return exc.code if isinstance(exc.code, int) else EXIT_USAGE

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    try:
        with db_factory() as db:
            if getattr(args, "needs_scraper", False):
                return args.handler(args, db, session_factory)
            return args.handler(args, db)
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
