"""Discovery tools: the model proposes through narrow doors; code decides the rest."""

import json

import pytest

from app.ai.schemas import PayeeLine, StatementOut
from app.contracts import MAX_BUTTON_LABEL, MAX_BUTTONS
from app.discovery.agent import (
    SUGGESTION_KINDS,
    DiscoveryTools,
    apply_answer,
    baseline_suggestions,
    build_suggestion,
    run_discovery,
)
from app.discovery.candidates import UNREFERENCED, Candidate
from app.discovery.directory import track_for
from app.fakes.ai import FakeAI
from tests.discovery.support import mailbox, scan


def cand(ref="4417", provider="Northline Mobile", ownership="unconfirmed"):
    return Candidate(
        account_ref=ref,
        provider=provider,
        service_label=f"{provider} {ref}",
        holder_name="",
        origin="x",
        ownership=ownership,
        evidence="e",
        track=track_for(provider),
    )


def tools(**kw):
    t = DiscoveryTools(candidates=kw.pop("candidates", []), **kw)
    t.grant_evidence("fwd:1", "Forwarded email")
    return t


def test_propose_rejects_unknown_evidence():
    t = tools()
    out = t.propose_candidate("Northline Mobile", "4417", "made-up")
    assert out.startswith("Rejected")
    assert t.candidates == []


def test_propose_rejects_empty_provider():
    t = tools()
    assert t.propose_candidate("  ", "4417", "fwd:1").startswith("Rejected")
    assert t.candidates == []


def test_propose_is_unconfirmed_and_has_no_ownership_argument():
    t = tools()
    t.propose_candidate("Crescent Bank", "99", "fwd:1")
    assert t.candidates[0].ownership == "unconfirmed"
    assert t.candidates[0].track == "financial"
    with pytest.raises(TypeError):
        t.propose_candidate("X", "1", "fwd:1", ownership="confirmed")  # type: ignore[call-arg]


def test_propose_never_moves_ownership_on_merge():
    t = tools(candidates=[cand(ownership="removed")])
    t.propose_candidate("Northline Mobile", "4417", "fwd:1")
    assert len(t.candidates) == 1
    assert t.candidates[0].ownership == "removed"
    assert "fwd:1" in t.candidates[0].evidence_ids


def test_unreferenced_never_merges():
    t = tools()
    t.propose_candidate("Gym", "", "fwd:1")
    t.propose_candidate("Gym", "", "fwd:1")
    assert [c.account_ref for c in t.candidates] == [UNREFERENCED, UNREFERENCED]


def test_same_ref_merges_once():
    t = tools()
    t.propose_candidate("Northline Mobile", "4417", "fwd:1")
    t.propose_candidate("Northline Mobile", "4417", "fwd:1")
    assert len(t.candidates) == 1


def test_model_text_is_truncated():
    t = tools()
    t.propose_candidate("P" * 500, "R" * 500, "fwd:1", "L" * 500)
    c = t.candidates[0]
    assert len(c.provider) <= 80 and len(c.account_ref) <= 40 and len(c.service_label) <= 80


@pytest.mark.parametrize(
    "text",
    [
        "I found everything for you",
        "That's it, the search is complete",
        "These are all his accounts",
        "Nothing else to find",
    ],
)
def test_suggest_rejects_overclaims(text):
    t = tools(candidates=[cand()])
    out = build_suggestion(t, kind="which_account", text=text, why="w", target="4417")
    assert isinstance(out, str) and out.startswith("Rejected")
    assert t.suggestions == []


def test_suggest_rejects_unknown_kind_and_empty_text():
    t = tools()
    assert build_suggestion(t, kind="send_email", text="hi", why="w") == (
        "Rejected: unknown suggestion kind."
    )
    assert isinstance(build_suggestion(t, kind="where_to_look", text="  ", why="w"), str)


def test_which_account_needs_a_real_target():
    t = tools(candidates=[cand()])
    assert isinstance(
        build_suggestion(t, kind="which_account", text="Is this his?", why="w", target="nope"), str
    )
    ok = build_suggestion(t, kind="which_account", text="Is this his?", why="w", target="4417")
    assert not isinstance(ok, str)


def test_run_locator_and_handback_targets_are_validated():
    t = tools()
    assert isinstance(build_suggestion(t, kind="run_locator", text="x", why="w", target="z"), str)
    assert isinstance(
        build_suggestion(t, kind="prepare_handback", text="x", why="w", target="z"), str
    )
    assert not isinstance(
        build_suggestion(t, kind="prepare_handback", text="x", why="w", target="probate"), str
    )


def test_where_to_look_unknown_target_falls_back():
    t = tools()
    s = build_suggestion(t, kind="where_to_look", text="Check post", why="w", target="zzz")
    assert s.target == "post"


def test_duplicate_suggestion_rejected():
    t = tools(candidates=[cand()])
    kw = dict(kind="which_account", text="Is this his?", why="w", target="4417")
    assert not isinstance(build_suggestion(t, **kw), str)
    assert build_suggestion(t, **kw) == "Already suggested."
    assert len(t.suggestions) == 1


def test_options_are_code_built_and_fit_channels():
    t = tools(candidates=[cand()])
    for kind in SUGGESTION_KINDS:
        target = {
            "which_account": "4417",
            "run_locator": "policy",
            "prepare_handback": "probate",
            "where_to_look": "post",
            "what_matters": "",
        }[kind]
        s = build_suggestion(t, kind=kind, text="A kind note", why="w", target=target)
        assert not isinstance(s, str), kind
        assert 1 <= len(s.options) <= MAX_BUTTONS
        assert all(len(o.label) <= MAX_BUTTON_LABEL for o in s.options)
        assert all(o.id.startswith(f"sg:{s.id}:") for o in s.options)


def test_apply_answer_confirms_only_through_a_button():
    t = tools(candidates=[cand()])
    baseline_suggestions(t)
    s = t.suggestions[0]
    assert t.candidates[0].ownership == "unconfirmed"
    got, reply = apply_answer(t, f"sg:{s.id}:own")
    assert got is s and t.candidates[0].ownership == "confirmed"
    assert "his" in reply


@pytest.mark.parametrize("code,state", [("not", "removed"), ("unsure", "needs_check")])
def test_apply_answer_other_ownership_choices(code, state):
    t = tools(candidates=[cand()])
    baseline_suggestions(t)
    apply_answer(t, f"sg:{t.suggestions[0].id}:{code}")
    assert t.candidates[0].ownership == state


@pytest.mark.parametrize("button", ["", "sg", "sg:1", "x:1:own", "sg:1:own:extra", "sg:99:own"])
def test_apply_answer_rejects_malformed_or_unknown(button):
    t = tools(candidates=[cand()])
    baseline_suggestions(t)
    got, _ = apply_answer(t, button)
    assert got is None
    assert t.candidates[0].ownership == "unconfirmed"


def test_apply_answer_bad_code_does_not_change_ownership():
    t = tools(candidates=[cand()])
    baseline_suggestions(t)
    _, reply = apply_answer(t, f"sg:{t.suggestions[0].id}:confirmed")
    assert reply == "I couldn't record that."
    assert t.candidates[0].ownership == "unconfirmed"


def test_apply_answer_is_single_use():
    t = tools(candidates=[cand()])
    baseline_suggestions(t)
    bid = f"sg:{t.suggestions[0].id}:not"
    apply_answer(t, bid)
    got, reply = apply_answer(t, f"sg:{t.suggestions[0].id}:own")
    assert got is None and "already answered" in reply
    assert t.candidates[0].ownership == "removed"


def test_apply_answer_locator_and_handback_prepare_text():
    t = tools(candidates=[cand("1", "Meridian Life"), cand("2", "Crescent Bank", "confirmed")])
    baseline_suggestions(t)
    loc = next(s for s in t.suggestions if s.kind == "run_locator")
    _, reply = apply_answer(t, f"sg:{loc.id}:prep")
    assert "You submit it" in reply and "policy" in t.locators_started
    hand = next(s for s in t.suggestions if s.kind == "prepare_handback")
    _, reply = apply_answer(t, f"sg:{hand.id}:prep")
    assert "does not file" in reply


def test_apply_answer_later_dismisses():
    t = tools(candidates=[cand("2", "Crescent Bank")])
    baseline_suggestions(t)
    wl = next(s for s in t.suggestions if s.kind == "where_to_look")
    s, _ = apply_answer(t, f"sg:{wl.id}:later")
    assert s.status == "dismissed"


def test_baseline_skips_unreferenced_ownership_question():
    t = tools(candidates=[cand(UNREFERENCED)])
    baseline_suggestions(t)
    assert not any(s.kind == "which_account" for s in t.suggestions)


async def test_tool_budget():
    t = tools(max_calls=2)
    t.list_documents()
    t.locator_catalogue()
    with pytest.raises(PermissionError):
        t.list_documents()
    assert len(t.calls) == 2


async def test_no_inbox_connected_is_explicit():
    t = tools()
    assert "No household inbox" in await t.search_inbox_headers(["gym"])
    assert "No household inbox" in await t.read_message("m1")


async def test_read_requires_tick_and_grants_evidence_after():
    s = scan(mailbox())
    t = tools(scan=s)
    rows = json.loads(await t.search_inbox_headers(["bill"]))["headers"]
    assert rows
    mid = rows[0]["id"]
    assert "Not ticked" in await t.read_message(mid)
    assert f"inbox:{mid}" not in t.evidence
    s.tick([mid], by="sara")
    body = json.loads(await t.read_message(mid))
    assert body["evidence_id"] == f"inbox:{mid}"
    assert t.propose_candidate("Northline Mobile", "4417", body["evidence_id"]).startswith(
        "Proposed"
    )


async def test_ask_to_read_does_not_tick():
    s = scan(mailbox())
    t = tools(scan=s)
    await t.search_inbox_headers([])
    t.ask_to_read(["m1", "bogus"])
    assert t.read_requests == ["m1"]
    assert s.ticked == set()


async def test_search_terms_limited_to_three():
    from tests.discovery.support import RecordingSearch

    client = RecordingSearch()
    t = tools(scan=scan(client))
    await t.search_inbox_headers(["a", "b", "c", "d", "e"])
    assert '"d"' not in client.queries[0] and '"c"' in client.queries[0]


async def test_run_discovery_falls_back_when_runner_raises():
    t = tools(candidates=[cand()])

    async def boom(_tools):
        raise RuntimeError("model down with a secret body")

    out = await run_discovery(t, boom)
    assert [s.kind for s in out] == ["which_account"]


async def test_run_discovery_without_runner_and_runner_suggestions_kept():
    t = tools(candidates=[cand()])

    async def runner(tl):
        tl.suggest_to_family("where_to_look", "Check the post", "w", "post")

    out = await run_discovery(t, runner)
    assert {s.kind for s in out} == {"where_to_look", "which_account"}
    assert [s.kind for s in await run_discovery(tools(), None)] == []


def _statement():
    return StatementOut(
        lines=[
            PayeeLine(
                payee="FitLife Gym", reference="G-1", amount="19.99", date="1 Mar", quote="FITLIFE"
            ),
            PayeeLine(
                payee="StreamBox", reference=None, amount="9.99", date="2 Mar", quote="STREAMBOX"
            ),
            PayeeLine(
                payee="StreamBox", reference=None, amount="9.99", date="2 Apr", quote="STREAMBOX"
            ),
        ]
    )


async def test_statement_payees_rejects_unknown_document():
    t = tools(ai=FakeAI())
    assert (await t.statement_payees("nope")).startswith("Rejected")
    assert t.candidates == []


async def test_statement_payees_makes_unconfirmed_candidates_and_never_merges_unreferenced():
    from app.contracts import ChatMessage
    from app.discovery.candidates import STATEMENT_SYSTEM

    ai = FakeAI()
    ai.register_structured(
        "document_reader",
        StatementOut,
        [
            ChatMessage(role="system", content=STATEMENT_SYSTEM),
            ChatMessage(role="user", content="statement text"),
        ],
        _statement(),
    )
    t = tools(ai=ai)
    t.grant_document("d1", "Bank statement", text="statement text")
    out = json.loads(await t.statement_payees("d1"))
    assert out["evidence_id"] == "doc:d1"
    assert len(t.candidates) == 3
    assert all(c.ownership == "unconfirmed" for c in t.candidates)
    assert [c.account_ref for c in t.candidates].count(UNREFERENCED) == 2
    assert t.propose_candidate("StreamBox", "S1", "doc:d1").startswith("Proposed")
