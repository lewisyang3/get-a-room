import logging
import os
import signal
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session, sessionmaker

import ingestion.cli
from app.models.models import ImportRun, ImportStatus, Meeting, Term, TermStatus
from ingestion.cli import main
from tests.ingestion.conftest import (
    FakeResponse,
    FakeSession,
    listing_handler,
    persist_prior_sections,
)

SOURCE_URL = "https://classes.berkeley.edu/taxonomy/term/8573"


@pytest.fixture
def cli(db: Session, db_engine):
    """Runs the CLI against the test database; `db` truncates afterwards."""
    db_factory = sessionmaker(bind=db_engine, autoflush=False)

    def run(*argv: str, session: FakeSession | None = None) -> int:
        def session_factory() -> FakeSession:
            run.scraper_builds += 1
            if session is None:
                raise AssertionError("the command built a scraper session")
            return session

        code = main(list(argv), db_factory=db_factory, session_factory=session_factory)
        db.expire_all()
        return code

    # How many scraper sessions the command built, across calls.
    run.scraper_builds = 0
    return run


def _create_args(
    name: str = "Fall 2026",
    start: str = "2026-08-19",
    end: str = "2026-12-18",
    source_url: str = SOURCE_URL,
) -> list[str]:
    return [
        "term",
        "create",
        "--name",
        name,
        "--start",
        start,
        "--end",
        end,
        "--source-url",
        source_url,
    ]


def test_term_create_stores_the_term_with_defaults(cli, db: Session, capsys):
    assert cli(*_create_args()) == 0

    term = db.query(Term).one()
    assert term.name == "Fall 2026"
    assert (term.start_date, term.end_date) == (date(2026, 8, 19), date(2026, 12, 18))
    assert term.source_url == SOURCE_URL
    assert term.timezone == "America/Los_Angeles"
    assert term.status == TermStatus.ACTIVE
    out = capsys.readouterr().out
    assert f"Created term {term.term_id}: Fall 2026" in out
    assert "taxonomy term 8573" in out


def test_term_create_stores_explicit_timezone_and_status(cli, db: Session):
    args = _create_args() + ["--timezone", "America/New_York", "--status", "archived"]
    assert cli(*args) == 0

    term = db.query(Term).one()
    assert term.timezone == "America/New_York"
    assert term.status == TermStatus.ARCHIVED


def test_term_create_rejects_a_duplicate_name(cli, db: Session, capsys):
    assert cli(*_create_args()) == 0
    capsys.readouterr()

    assert cli(*_create_args(start="2027-01-20", end="2027-05-15")) == 2

    assert "already exists" in capsys.readouterr().err
    assert db.query(Term).count() == 1


@pytest.mark.parametrize("end", ["2026-08-19", "2026-08-01"])
def test_term_create_rejects_an_end_not_after_the_start(cli, db: Session, capsys, end):
    assert cli(*_create_args(end=end)) == 2

    assert "--start must be before --end" in capsys.readouterr().err
    assert db.query(Term).count() == 0


def test_term_create_rejects_a_malformed_date(cli, db: Session, capsys):
    assert cli(*_create_args(start="08/19/2026")) == 2

    assert "YYYY-MM-DD" in capsys.readouterr().err
    assert db.query(Term).count() == 0


def test_term_create_rejects_an_unknown_timezone(cli, db: Session, capsys):
    assert cli(*_create_args() + ["--timezone", "Mars/Olympus_Mons"]) == 2

    assert "unknown timezone" in capsys.readouterr().err
    assert db.query(Term).count() == 0


@pytest.mark.parametrize(
    "source_url",
    [
        "https://classes.berkeley.edu/search/class",
        "https://classes.berkeley.edu/taxonomy/term/85x",
    ],
)
def test_term_create_rejects_a_non_taxonomy_source_url(
    cli, db: Session, capsys, source_url
):
    assert cli(*_create_args(source_url=source_url)) == 2

    assert "invalid source URL" in capsys.readouterr().err
    assert db.query(Term).count() == 0


@pytest.mark.parametrize(
    "timezone",
    ["America", "posixrules", "Factory", "localtime", "Mars/Olympus_Mons", ""],
)
def test_term_create_rejects_a_non_location_timezone(
    cli, db: Session, capsys, timezone
):
    assert cli(*_create_args() + ["--timezone", timezone]) == 2

    err = capsys.readouterr().err
    assert "unknown timezone" in err
    assert "Traceback" not in err
    assert db.query(Term).count() == 0


@pytest.mark.parametrize(
    "name, message",
    [("   ", "can't be blank"), ("N" * 101, "the limit is 100")],
)
def test_term_create_rejects_a_blank_or_overlong_name(
    cli, db: Session, capsys, name, message
):
    assert cli(*_create_args(name=name)) == 2

    assert message in capsys.readouterr().err
    assert db.query(Term).count() == 0


def test_term_create_strips_the_name(cli, db: Session, capsys):
    assert cli(*_create_args(name="  Fall 2026 ")) == 0
    assert db.query(Term).one().name == "Fall 2026"
    capsys.readouterr()

    # Same name once stripped - a duplicate, even with a different taxonomy id.
    other_url = "https://classes.berkeley.edu/taxonomy/term/8600"
    assert cli(*_create_args(name="Fall 2026 ", source_url=other_url)) == 2
    assert "already exists" in capsys.readouterr().err
    # And lookups strip too.
    assert cli("term", "set-status", "Fall 2026 ", "archived") == 0


def test_term_create_rejects_an_overlong_source_url(cli, db: Session, capsys):
    long_url = "https://classes.berkeley.edu/taxonomy/term/" + "1" * 460

    assert cli(*_create_args(source_url=long_url)) == 2

    assert "the limit is 500" in capsys.readouterr().err
    assert db.query(Term).count() == 0


def test_term_create_rejects_a_taxonomy_id_already_in_use(cli, db: Session, capsys):
    assert cli(*_create_args()) == 0
    capsys.readouterr()

    # Same taxonomy id, spelled differently (trailing slash, host case).
    same_term = "https://CLASSES.berkeley.edu/taxonomy/term/8573/"
    assert cli(*_create_args(name="Fall 2026 copy", source_url=same_term)) == 2
    assert "already uses taxonomy term 8573" in capsys.readouterr().err

    other_url = "https://classes.berkeley.edu/taxonomy/term/8600"
    assert cli(*_create_args(name="Spring 2027", source_url=other_url)) == 0
    assert db.query(Term).count() == 2


def test_term_create_stores_the_canonical_source_url(cli, db: Session, capsys):
    assert (
        cli(
            *_create_args(source_url="https://CLASSES.berkeley.edu/taxonomy/term/8573/")
        )
        == 0
    )

    assert db.query(Term).one().source_url == SOURCE_URL
    capsys.readouterr()
    assert cli("term", "list") == 0
    assert SOURCE_URL in capsys.readouterr().out


def test_term_list_with_no_terms(cli, capsys):
    assert cli("term", "list") == 0

    assert capsys.readouterr().out.strip() == "No terms."


def test_term_list_orders_terms_by_start_date(cli, capsys):
    spring_url = "https://classes.berkeley.edu/taxonomy/term/8600"
    cli(
        *_create_args(
            name="Spring 2027",
            start="2027-01-20",
            end="2027-05-15",
            source_url=spring_url,
        )
    )
    cli(*_create_args(name="Fall 2026"))
    capsys.readouterr()

    assert cli("term", "list") == 0

    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split() == [
        "ID",
        "NAME",
        "START",
        "END",
        "STATUS",
        "PROCESSED",
        "SOURCE",
        "URL",
    ]
    assert "Fall 2026" in lines[1] and SOURCE_URL in lines[1]
    assert "Spring 2027" in lines[2]
    assert all(" never " in line for line in lines[1:])


@pytest.mark.parametrize("ref", ["id", "name"])
def test_term_set_status_by_id_or_name(cli, db: Session, capsys, ref):
    cli(*_create_args())
    term = db.query(Term).one()
    capsys.readouterr()

    target = str(term.term_id) if ref == "id" else term.name
    assert cli("term", "set-status", target, "archived") == 0

    assert db.query(Term).one().status == TermStatus.ARCHIVED
    assert "active -> archived" in capsys.readouterr().out


def test_term_set_status_to_the_current_status_is_a_no_op(cli, db: Session, capsys):
    cli(*_create_args())
    capsys.readouterr()

    assert cli("term", "set-status", "Fall 2026", "active") == 0

    assert "already active" in capsys.readouterr().out
    assert db.query(Term).one().status == TermStatus.ACTIVE


def test_term_set_status_resolves_a_numeric_name_when_no_id_matches(cli, db: Session):
    cli(*_create_args(name="2026"))

    assert cli("term", "set-status", "2026", "archived") == 0

    assert db.query(Term).one().status == TermStatus.ARCHIVED


def test_term_set_status_rejects_an_unknown_term(cli, capsys):
    assert cli("term", "set-status", "Nope 1999", "archived") == 2

    assert "no term matching 'Nope 1999'" in capsys.readouterr().err


def test_no_subcommand_is_a_usage_error(cli):
    assert cli() == 2
    assert cli("term") == 2


def test_help_exits_zero(cli, capsys):
    assert cli("--help") == 0
    assert cli("term", "create", "--help") == 0
    assert "--source-url" in capsys.readouterr().out


# --- import run -------------------------------------------------------------


@dataclass
class ClosingFakeSession(FakeSession):
    closed: bool = False

    def close(self) -> None:
        self.closed = True


def _session(*slugs: str) -> ClosingFakeSession:
    return ClosingFakeSession(listing_handler(*slugs))


def _import_args(term: str = "Fall 2026", *extra: str) -> list[str]:
    # A zero rate limit so no test sleeps between fake requests.
    return ["import", "run", term, "--rate-limit-seconds", "0", *extra]


@pytest.fixture
def created_term(cli, db: Session, capsys) -> Term:
    assert cli(*_create_args()) == 0
    capsys.readouterr()
    return db.query(Term).one()


def _import_runs(db: Session) -> list[ImportRun]:
    return db.query(ImportRun).order_by(ImportRun.import_id).all()


def test_import_run_completes_and_exits_0(cli, db: Session, created_term, caplog):
    caplog.set_level(logging.INFO)
    session = _session("lec-with-room", "ind-no-meetings")

    assert cli(*_import_args(), session=session) == 0

    [run] = _import_runs(db)
    assert run.status == ImportStatus.COMPLETED
    assert (
        run.records_read,
        run.records_imported,
        run.records_rejected,
        run.records_failed,
    ) == (2, 1, 1, 0)
    assert db.query(Meeting).filter_by(term_id=created_term.term_id).count() == 1
    taxonomy_paths = {p for p, _ in session.calls if p.startswith("/taxonomy/")}
    assert taxonomy_paths == {"/taxonomy/term/8573"}
    assert f"import {run.import_id} for term {created_term.term_id}" in caplog.text
    assert "COMPLETED" in caplog.text
    assert "2 read, 1 imported, 1 rejected, 0 failed" in caplog.text
    assert session.closed


def test_term_list_shows_when_the_last_import_completed(
    cli, db: Session, created_term, capsys
):
    assert cli(*_import_args(), session=_session("lec-with-room")) == 0
    [run] = _import_runs(db)
    capsys.readouterr()

    assert cli("term", "list") == 0

    expected = run.completed_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    assert expected in capsys.readouterr().out.splitlines()[1]


def test_import_run_exits_3_when_a_section_fails(
    cli, db: Session, created_term, caplog
):
    caplog.set_level(logging.INFO)

    code = cli(*_import_args(), session=_session("lec-with-room", "vanished"))

    assert code == 3
    [run] = _import_runs(db)
    assert run.status == ImportStatus.COMPLETED
    assert run.records_failed == 1
    assert any(
        r.levelno == logging.WARNING and "cleanup was skipped" in r.getMessage()
        for r in caplog.records
    )


def test_import_run_exits_1_when_the_import_aborts(
    cli, db: Session, created_term, caplog
):
    persist_prior_sections(db, created_term, "a", "b")
    session = _session()  # an empty listing

    assert cli(*_import_args(), session=session) == 1

    failed = _import_runs(db)[-1]
    assert failed.status == ImportStatus.FAILED
    assert f"import {failed.import_id} for term" in caplog.text
    assert "ImportAborted" in caplog.text
    assert {m.source_record_id for m in db.query(Meeting)} == {"a", "b"}
    assert session.closed


def test_import_run_exits_1_when_enumeration_fails(cli, db: Session, created_term):
    session = ClosingFakeSession(lambda path, params: FakeResponse(403, "Forbidden"))

    assert cli(*_import_args(), session=session) == 1

    assert _import_runs(db)[-1].status == ImportStatus.FAILED
    assert session.closed


def test_import_run_never_reports_an_older_failed_run_as_this_one(
    cli, db: Session, created_term, caplog, monkeypatch
):
    older = ImportRun(
        term_id=created_term.term_id,
        started_at=datetime.now(timezone.utc) - timedelta(days=1),
        source_url=created_term.source_url,
        status=ImportStatus.FAILED,
    )
    db.add(older)
    db.commit()

    def fails_without_recording(*args, **kwargs):
        raise RuntimeError("database went away")

    monkeypatch.setattr(ingestion.cli, "run_import", fails_without_recording)

    assert cli(*_import_args(), session=_session()) == 1

    assert "import (not recorded) for term" in caplog.text
    assert f"import {older.import_id} for term" not in caplog.text
    # Nothing else logged this failure, so the CLI must include the traceback.
    assert "Traceback" in caplog.text
    assert "database went away" in caplog.text


def test_import_run_rejects_an_unknown_term(cli, db: Session, capsys):
    assert cli(*_import_args("Nope 1999")) == 2

    assert "no term matching 'Nope 1999'" in capsys.readouterr().err
    assert _import_runs(db) == []
    assert cli.scraper_builds == 0


def test_import_run_refuses_an_archived_term_unless_allowed(
    cli, db: Session, created_term, capsys
):
    assert cli("term", "set-status", "Fall 2026", "archived") == 0
    capsys.readouterr()

    assert cli(*_import_args()) == 2
    assert "--allow-archived" in capsys.readouterr().err
    assert _import_runs(db) == []
    assert cli.scraper_builds == 0

    session = _session("lec-with-room")
    assert cli(*_import_args("Fall 2026", "--allow-archived"), session=session) == 0
    assert _import_runs(db)[-1].status == ImportStatus.COMPLETED


def test_import_run_rejects_a_term_without_a_source_url(cli, db: Session, capsys):
    # Not creatable through the CLI, which validates --source-url.
    db.add(
        Term(
            name="Legacy",
            start_date=date(2025, 1, 21),
            end_date=date(2025, 5, 16),
            source_url=None,
        )
    )
    db.commit()

    assert cli(*_import_args("Legacy")) == 2

    assert "can't be imported" in capsys.readouterr().err
    assert _import_runs(db) == []
    assert cli.scraper_builds == 0


@pytest.mark.parametrize(
    "option, value",
    [
        ("--max-pages", "0"),
        ("--max-pages", "abc"),
        ("--max-retire-fraction", "1.5"),
        ("--max-retire-fraction", "-0.1"),
        ("--max-retire-fraction", "abc"),
        ("--rate-limit-seconds", "-1"),
        ("--rate-limit-seconds", "abc"),
        ("--parser-version", "x" * 51),
    ],
)
def test_import_run_rejects_out_of_range_options(
    cli, db: Session, created_term, capsys, option, value
):
    assert cli("import", "run", "Fall 2026", option, value) == 2

    assert f"argument {option}" in capsys.readouterr().err
    assert _import_runs(db) == []
    assert cli.scraper_builds == 0


def test_import_run_passes_max_retire_fraction_through(cli, db: Session, created_term):
    """Retiring both prior sections exceeds the 0.5 default - it only
    completes if --max-retire-fraction actually reaches run_import."""
    persist_prior_sections(db, created_term, "a", "b")

    code = cli(
        *_import_args("Fall 2026", "--max-retire-fraction", "1.0"),
        session=_session("ind-no-meetings"),
    )

    assert code == 0
    assert db.query(Meeting).count() == 0


def test_import_run_records_the_parser_version(cli, db: Session, created_term):
    code = cli(
        *_import_args("Fall 2026", "--parser-version", "v9"),
        session=_session("lec-with-room"),
    )

    assert code == 0
    assert _import_runs(db)[-1].parser_version == "v9"


def test_import_run_defaults_the_rate_limit_from_settings(
    cli, created_term, monkeypatch
):
    monkeypatch.setattr(
        ingestion.cli,
        "get_settings",
        lambda: SimpleNamespace(scraper_rate_limit_seconds=0.0),
    )
    calls = []
    real_run_import = ingestion.cli.run_import

    def spy(*args, **kwargs):
        calls.append(kwargs)
        return real_run_import(*args, **kwargs)

    monkeypatch.setattr(ingestion.cli, "run_import", spy)

    code = cli("import", "run", "Fall 2026", session=_session("lec-with-room"))

    assert code == 0
    assert [call["rate_limit_seconds"] for call in calls] == [0.0]


def _interrupting_session(interrupt) -> ClosingFakeSession:
    listing = listing_handler("lec-with-room")

    def handler(path: str, params: dict | None) -> FakeResponse:
        if path.startswith("/content/"):
            interrupt()
        return listing(path, params)

    return ClosingFakeSession(handler)


def test_import_run_records_a_ctrl_c_and_exits_130(
    cli, db: Session, created_term, caplog
):
    def ctrl_c():
        raise KeyboardInterrupt

    session = _interrupting_session(ctrl_c)

    assert cli(*_import_args(), session=session) == 130

    failed = _import_runs(db)[-1]
    assert failed.status == ImportStatus.FAILED
    assert failed.error_message == "KeyboardInterrupt"
    assert f"import {failed.import_id} for term" in caplog.text
    assert "INTERRUPTED" in caplog.text
    assert db.query(Meeting).count() == 0
    assert session.closed


def test_import_run_records_a_sigterm_and_exits_143(
    cli, db: Session, created_term, caplog
):
    previous_handler = signal.getsignal(signal.SIGTERM)
    session = _interrupting_session(lambda: os.kill(os.getpid(), signal.SIGTERM))

    assert cli(*_import_args(), session=session) == 143

    failed = _import_runs(db)[-1]
    assert failed.status == ImportStatus.FAILED
    assert failed.error_message == "interrupted by SIGTERM"
    assert "INTERRUPTED" in caplog.text
    assert session.closed
    assert signal.getsignal(signal.SIGTERM) is previous_handler
