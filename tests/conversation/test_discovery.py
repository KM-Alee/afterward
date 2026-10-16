"""Candidates merge only on account_ref. Coverage never says the search is finished."""

from app.discovery.candidates import Candidate, merge_candidate
from app.discovery.coverage import Coverage, coverage_panel, render_coverage


def test_same_provider_with_different_refs_stays_separate():
    first = Candidate("4417", "Northline Mobile", "line 4417", "Yusuf Malik", "forwarded")
    second = Candidate("2290", "Northline Mobile", "line 2290", "", "photo")
    merged = merge_candidate(merge_candidate([], first), second)
    assert [item.account_ref for item in merged] == ["4417", "2290"]


def test_matching_ref_merges_and_does_not_confirm():
    first = Candidate(
        "4417", "Northline Mobile", "line 4417", "Yusuf Malik", "forwarded", evidence="bill"
    )
    second = Candidate(
        "4417", "Northline Mobile", "line 4417", "Yusuf Malik", "forwarded", evidence="receipt"
    )
    merged = merge_candidate(merge_candidate([], first), second)
    assert len(merged) == 1
    assert "bill" in merged[0].evidence
    assert "receipt" in merged[0].evidence
    assert merged[0].ownership == "unconfirmed"


def test_coverage_lists_gaps_and_has_no_complete_flag():
    candidates = [
        Candidate(
            "4417",
            "Northline Mobile",
            "Mobile line ending 4417",
            "Yusuf",
            "forwarded",
            "confirmed",
        ),
        Candidate("2290", "Northline Mobile", "Mobile line ending 2290", "", "photo"),
    ]
    coverage = coverage_panel(candidates, emails=6, photos=4)
    assert set(Coverage.__dataclass_fields__) == {
        "searched",
        "not_searched",
        "unconfirmed",
        "where_else",
    }
    assert coverage.searched[0] == "6 emails Sara forwarded"
    assert "Yusuf's own inbox (no access, by design)" in coverage.not_searched
    assert coverage.unconfirmed == ("Mobile line ending 2290",)
    assert "Bank statements: look for direct debits" in coverage.where_else
    text = render_coverage(coverage, emails=6, photos=4, total=2)
    lowered = text.lower()
    assert "looks complete" not in lowered
    assert "complete discovery" not in lowered
    assert "every account" not in lowered
    assert "1 need you to confirm" in text
