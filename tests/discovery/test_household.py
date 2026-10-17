"""Household scan: the model can narrow a search, never widen it or read unticked mail."""

import pytest

from app.discovery.household import (
    AuthorityMissing,
    HouseholdScan,
    NotOwner,
    NotTicked,
    scope_query,
)
from tests.discovery.support import RecordingSearch, scan


def test_scope_query_requires_an_anchor():
    with pytest.raises(ValueError):
        scope_query([], None)
    with pytest.raises(ValueError):
        scope_query(["  "], "")


def test_narrow_terms_are_anded_not_ored():
    base = scope_query(["Yusuf Malik"], None)
    narrowed = scope_query(["Yusuf Malik"], None, narrow=["gym"])
    assert narrowed.startswith(base.rsplit(" newer_than", 1)[0])
    assert '"gym"' in narrowed
    assert " OR gym" not in narrowed and "gym OR" not in narrowed


def test_injection_characters_are_stripped():
    query = scope_query(["Yusuf Malik"], None, narrow=['x" OR in:anywhere (label:all) -in:spam'])
    assert "(label:all)" not in query and ":" not in query.replace("newer_than:3y", "")
    assert query.count('"') % 2 == 0
    evil_name = scope_query(['Yusuf" OR from:*'], None)
    assert "from:*" not in evil_name


def test_window_is_clamped():
    assert scope_query(["A"], None, years=99).endswith("newer_than:10y")
    assert scope_query(["A"], None, years=0).endswith("newer_than:1y")


async def test_search_is_headers_only():
    client = RecordingSearch()
    s = scan(client)
    found = await s.search()
    assert [h.id for h in found] == ["x1"]
    assert client.gets == []
    assert s.read == set()


async def test_read_denied_until_ticked():
    client = RecordingSearch()
    s = scan(client)
    await s.search()
    with pytest.raises(NotTicked):
        await s.read_message("x1")
    assert client.gets == []
    s.tick(["x1"], by="sara")
    assert await s.read_message("x1") == "body"


async def test_only_owner_can_tick():
    s = scan(RecordingSearch())
    await s.search()
    with pytest.raises(NotOwner):
        s.tick(["x1"], by="mallory")
    assert s.ticked == set()


async def test_unknown_ids_are_not_ticked():
    s = scan(RecordingSearch())
    await s.search()
    assert s.tick(["nope"], by="sara") == []
    assert s.ticked == set()


def test_deceased_mailbox_needs_stated_authority():
    with pytest.raises(AuthorityMissing):
        scan(account_of="deceased")
    with pytest.raises(AuthorityMissing):
        scan(account_of="deceased", stated_authority="   ")
    assert scan(account_of="deceased", stated_authority="his executor")


def test_bad_account_of_rejected():
    with pytest.raises(ValueError):
        scan(account_of="someone")


def test_can_send_is_false():
    assert HouseholdScan.can_send.fget(scan()) is False


async def test_coverage_line_wording():
    s = scan(RecordingSearch())
    assert s.coverage_line() is None
    await s.search()
    line = s.coverage_line()
    assert line == "Household inbox: 1 messages about accounts, 0 read with your OK, 1 not read"
    assert "all" not in line.lower().split() and "complete" not in line.lower()


async def test_deceased_coverage_line_names_authority():
    s = scan(RecordingSearch(), account_of="deceased", stated_authority="his executor")
    await s.search()
    assert "stated: his executor" in s.coverage_line()
    assert "read-only" in s.coverage_line()
