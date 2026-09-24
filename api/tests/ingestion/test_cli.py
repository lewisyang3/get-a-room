from datetime import date

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.models.models import Term, TermStatus
from ingestion.cli import main

SOURCE_URL = "https://classes.berkeley.edu/taxonomy/term/8573"


@pytest.fixture
def cli(db: Session, db_engine):
    """Runs the CLI against the test database; `db` truncates afterwards."""
    db_factory = sessionmaker(bind=db_engine, autoflush=False)

    def run(*argv: str) -> int:
        code = main(list(argv), db_factory=db_factory)
        db.expire_all()
        return code

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


def test_term_list_with_no_terms(cli, capsys):
    assert cli("term", "list") == 0

    assert capsys.readouterr().out.strip() == "No terms."


def test_term_list_orders_terms_by_start_date(cli, capsys):
    cli(*_create_args(name="Spring 2027", start="2027-01-20", end="2027-05-15"))
    cli(*_create_args(name="Fall 2026"))
    capsys.readouterr()

    assert cli("term", "list") == 0

    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split() == ["ID", "NAME", "START", "END", "STATUS", "SOURCE", "URL"]
    assert "Fall 2026" in lines[1] and SOURCE_URL in lines[1]
    assert "Spring 2027" in lines[2]


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
