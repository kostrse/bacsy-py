"""The `Portfolio` snapshot and its settlement-term views."""

from __future__ import annotations

from bacsy.models import DEFAULT_TERM, BasePosition, Portfolio, Term


def line(name: str, term: str | None) -> dict[str, object]:
    return {"displayName": name, "type": "depoLimit", "term": term, "quantity": 1}


def test_lines_keep_every_term_in_order() -> None:
    portfolio = Portfolio.model_validate(
        [line("SBER", "T0"), line("SBER", "T365"), line("RUB", "T0"), line("RUB", "T365")]
    )

    assert [(p.display_name, p.term) for p in portfolio.lines] == [
        ("SBER", Term.T0),
        ("SBER", Term.T365),
        ("RUB", Term.T0),
        ("RUB", Term.T365),
    ]
    assert portfolio.terms == [Term.T0, Term.T365]


def test_positions_default_to_the_planned_term() -> None:
    portfolio = Portfolio.model_validate([line("SBER", "T0"), line("SBER", "T365")])

    assert DEFAULT_TERM is Term.T365
    assert [p.term for p in portfolio.positions()] == [Term.T365]
    assert [p.term for p in portfolio.positions(Term.T0)] == [Term.T0]
    assert portfolio.positions(Term.T2) == []


def test_lines_without_a_term_belong_to_no_view() -> None:
    portfolio = Portfolio.model_validate([line("SBER", None), line("RUB", "T365")])

    assert len(portfolio.lines) == 2
    assert portfolio.terms == [Term.T365]
    assert [p.display_name for p in portfolio.positions()] == ["RUB"]
    assert list(portfolio.by_term()) == [Term.T365]


def test_by_term_groups_including_unknown_terms() -> None:
    portfolio = Portfolio.model_validate(
        [line("SBER", "T365"), line("SBER", "T3"), line("RUB", "T3")]
    )

    grouped = portfolio.by_term()

    assert [str(term) for term in grouped] == ["T365", "T3"]
    assert [p.display_name for p in grouped[Term("T3")]] == ["SBER", "RUB"]
    assert all(isinstance(p, BasePosition) for group in grouped.values() for p in group)
    unknown = portfolio.terms[1]
    assert not unknown.is_known


def test_empty_snapshot() -> None:
    portfolio = Portfolio.model_validate([])

    assert portfolio.lines == []
    assert portfolio.terms == []
    assert portfolio.positions() == []
    assert portfolio.by_term() == {}
