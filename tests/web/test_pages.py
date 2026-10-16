"""Page rendering for the desk, family view, provider console and proofs."""

from uuid import uuid4

from app.web.proofs import PROOF_CASES
from app.web.render import render_status_html
from app.web.state import EMPTY_CASE_ID
from tests.web.conftest import login, token_for


def test_landing_hides_the_passcode_and_rejects_a_wrong_one(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "Demo passcode" in page.text
    assert "fixture-passcode" not in page.text
    assert "You tell it once" in page.text
    denied = client.post("/access", data={"passcode": "not-the-passcode"})
    assert denied.status_code == 401
    assert "did not work" in denied.text
    blank = client.post("/access", data={"passcode": ""})
    assert blank.status_code == 401
    assert "Enter the demo passcode" in blank.text


def test_desk_requires_the_passcode_and_renders_the_case(client):
    surface = client.app.state.surface
    locked = client.get(f"/desk/{surface.demo_case_id}")
    assert locked.status_code == 401
    assert "Demo passcode" in locked.text
    login(client)
    page = client.get(f"/desk/{surface.demo_case_id}")
    assert page.status_code == 200
    assert "Yusuf Malik" in page.text
    assert "Sara asked for" in page.text
    assert "Northline said" in page.text
    assert "Voicemail kept" in page.text
    assert "Broken" in page.text
    assert "Not stated" in page.text
    assert "Not approved" in page.text
    assert "Mailbox disconnected" in page.text
    assert "may not have sent" in page.text
    assert "Delivery is uncertain" in page.text
    assert "+14 days" in page.text
    assert "+35 days" in page.text
    assert "Confidential compute: not verified" in page.text
    assert "does not extend to the" in page.text
    assert "Service" in page.text
    assert "Money" in page.text
    assert "Documents" in page.text
    assert "Next" in page.text
    assert "Provider confirmed in writing" in page.text
    assert "No measured turn times yet" in page.text
    assert "Browser call, not a phone call" in page.text


def test_empty_desk_and_unknown_case(client):
    login(client)
    empty = client.get(f"/desk/{EMPTY_CASE_ID}")
    assert empty.status_code == 200
    assert "No case open" in empty.text
    assert "No events yet" in empty.text
    missing = client.get(f"/desk/{uuid4()}")
    assert missing.status_code == 404
    assert "not valid" in missing.text


def test_case_clock_moves_demo_time_only(client):
    login(client)
    surface = client.app.state.surface
    moved = client.post(
        f"/api/cases/{surface.demo_case_id}/clock",
        data={"advance_days": "14"},
        follow_redirects=True,
    )
    assert moved.status_code == 200
    assert "20 Mar 2026" in moved.text
    rejected = client.post(
        f"/api/cases/{surface.demo_case_id}/clock",
        data={"advance_days": "3"},
    )
    assert rejected.status_code == 422
    assert "only moves 14 or 35" in rejected.text


def test_family_view_matches_the_decision_card(client):
    surface = client.app.state.surface
    token = token_for(surface.family_tokens, surface.demo_case_id)
    page = client.get(f"/family/{token}")
    assert page.status_code == 200
    assert "Northline says it's done. It isn't." in page.text
    assert "Ask them to fix it" in page.text
    assert "Call them for me" in page.text
    assert "Accept anyway" in page.text
    assert "Provider confirmed in writing" in page.text
    assert page.text.count('name="choice"') == 3
    empty = token_for(surface.family_tokens, EMPTY_CASE_ID)
    quiet = client.get(f"/family/{empty}")
    assert quiet.status_code == 200
    assert "Nothing needs you" in quiet.text
    assert client.get("/family/not-a-real-token").status_code == 404


def test_provider_console_sends_through_the_fake_mailbox(client):
    surface = client.app.state.surface
    token = token_for(surface.provider_tokens, surface.demo_case_id)
    page = client.get(f"/provider/{token}")
    assert page.status_code == 200
    assert "Reply as a provider" in page.text
    assert "Northline Mobile" in page.text
    assert "Write my own" in page.text
    empty = client.post(
        "/api/provider/send",
        data={"token": token, "provider": "northline", "variant": "", "text": "  "},
        follow_redirects=False,
    )
    assert empty.status_code == 422
    assert "Write a reply" in empty.text
    assert surface.mailbox.sent == []
    sent = client.post(
        "/api/provider/send",
        data={
            "token": token,
            "provider": "northline",
            "variant": "nl_contradictory",
            "text": "We moved the line, and the voicemail will reset.",
        },
        follow_redirects=True,
    )
    assert sent.status_code == 200
    assert "Recorded in the demo mailbox as sent" in sent.text
    assert "was not contacted" in sent.text
    assert len(surface.mailbox.sent) == 1
    assert "voicemail will reset" in surface.mailbox.sent[0].text
    assert client.get("/provider/not-a-real-token").status_code == 404
    quiet = client.get(f"/provider/{token_for(surface.provider_tokens, EMPTY_CASE_ID)}")
    assert quiet.status_code == 200
    assert "Nothing to answer yet" in quiet.text


def test_proofs_list_fourteen_cases_without_inventing_results(client):
    login(client)
    page = client.get("/proofs")
    assert page.status_code == 200
    assert "Nothing has been run" in page.text
    assert page.text.count("Not run") == len(PROOF_CASES) == 14
    assert "We received your request" in page.text
    assert "Did you finish everything?" in page.text
    ran = client.post("/api/proofs/run")
    assert ran.status_code == 200
    assert "have not been run" in ran.text
    assert ran.text.count("Not run") == 14
    assert "holding" not in ran.text or "Not run" in ran.text
    locked = client.cookies.clear()
    assert locked is None
    assert client.get("/proofs").status_code == 401


def test_status_template_is_not_a_route(client):
    assert client.get("/status").status_code == 404
    html = render_status_html(
        {
            "page": "status",
            "nav": [],
            "phone_calls": "disabled",
            "db_reachable": False,
            "channels": {"telegram": "webhook", "whatsapp": "disabled"},
            "models": {
                "stt": "gpt-transcribe",
                "fast": "gpt-6-luna",
                "accurate": "gpt-6.1-sol",
                "tts": "gpt-4o-mini-tts",
                "realtime": "gpt-realtime-2.1",
            },
            "boundary_note": "Confidential compute protects our compute and storage.",
        }
    )
    assert "Phone calls: disabled" in html
    assert "gpt-realtime-2.1" in html
    assert "fixture-passcode" not in html
    css = client.get("/static/css/tokens.css")
    assert css.status_code == 200
    assert "Newsreader" in css.text
