"""Coverage never promises completeness."""

from app.discovery.coverage import NOT_SEARCHED, coverage_panel, render_coverage


def test_his_inbox_stays_unsearched_unless_connected():
    panel = coverage_panel([], emails=1, photos=0)
    assert NOT_SEARCHED[0] in panel.not_searched
    connected = coverage_panel(
        [], emails=1, photos=0, sources=("His inbox, stated: executor",), his_inbox_connected=True
    )
    assert NOT_SEARCHED[0] not in connected.not_searched
    assert "His inbox, stated: executor" in connected.searched
    assert "Other email addresses he used" in connected.not_searched


def test_government_and_credit_always_not_searched():
    panel = coverage_panel([], emails=0, photos=0, his_inbox_connected=True)
    assert "Government, court and tax records" in panel.not_searched
    assert "His credit file" in panel.not_searched


def test_rendered_line_does_not_claim_completeness():
    panel = coverage_panel([], emails=2, photos=1)
    line = render_coverage(panel, emails=2, photos=1, total=3).lower()
    for word in ("complete", "everything", "all accounts", "nothing else"):
        assert word not in line
