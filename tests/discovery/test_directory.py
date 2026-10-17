"""Directory tracks come from data. Hand-back words win. Nothing is allowed unconfirmed."""

import pytest

from app.discovery.directory import (
    DIRECTORY,
    FINANCIAL,
    HANDBACK,
    HANDBACK_STEPS,
    INSURANCE,
    LOCATORS,
    ORDINARY,
    UNKNOWN,
    allowed_actions,
    filter_actions,
    track_for,
)


@pytest.mark.parametrize("name", ["HMRC", "Probate Registry", "Federal Board of Revenue", "NADRA"])
def test_handback_words_win(name):
    assert track_for(name) == HANDBACK


def test_handback_beats_directory_entry():
    assert track_for("Crescent Bank Probate Team") == HANDBACK


def test_directory_and_keyword_tracks():
    assert track_for("City Power") == ORDINARY
    assert track_for("crescent bank") == FINANCIAL
    assert track_for("Acme Building Society") == FINANCIAL
    assert track_for("Acme Assurance") == INSURANCE
    assert track_for("Totally Unknown Co") == UNKNOWN
    assert track_for("") == UNKNOWN


@pytest.mark.parametrize("ownership", ["unconfirmed", "removed", "needs_check"])
@pytest.mark.parametrize("track", [ORDINARY, FINANCIAL, INSURANCE, HANDBACK, UNKNOWN])
def test_nothing_allowed_unless_confirmed(ownership, track):
    assert allowed_actions(ownership=ownership, track=track) == frozenset()


def test_handback_has_no_send():
    allowed = allowed_actions(ownership="confirmed", track=HANDBACK)
    assert allowed and not any("send" in action for action in allowed)
    assert "notify_with_approval" not in allowed


def test_filter_drops_model_proposed_actions():
    got = filter_actions(
        ownership="confirmed",
        track=FINANCIAL,
        proposed=["notify_with_approval", "send_with_approval", "close_account"],
    )
    assert got == ["notify_with_approval"]
    assert filter_actions(ownership="unconfirmed", track=ORDINARY, proposed=["plan"]) == []


def test_unknown_track_is_plan_only():
    assert allowed_actions(ownership="confirmed", track="weird") == frozenset()
    assert allowed_actions(ownership="confirmed", track=UNKNOWN) == {"plan"}


def test_directory_is_fictional_and_locators_are_run_by_family():
    assert DIRECTORY and all(loc.fictional for loc in LOCATORS)
    assert set(HANDBACK_STEPS) == {"copies", "probate", "government", "claim"}


@pytest.mark.parametrize("name", ["First Insurance", "Syntax Labs", "Firstline Bank"])
def test_handback_words_match_whole_words_only(name):
    assert track_for(name) != HANDBACK


def test_plural_handback_word_matches():
    assert track_for("Benefits Agency") == HANDBACK
