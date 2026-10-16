"""The demo desk can be saved and reloaded without the live sockets."""

from app.contracts import SentRecord
from app.web.snapshot import dump_surface, load_surface
from app.web.state import build_surface


def test_snapshot_keeps_the_story_and_login():
    surface = build_surface("fixture-passcode")
    board = surface.cases[surface.demo_case_id]
    board.family_choice = "ask"
    board.clock_case.clock_offset_s = 14 * 86400
    surface.sessions.add("session-fixture")
    surface.mailbox.sent.append(
        SentRecord(
            mailbox="family@example.com",
            gmail_id="g1",
            thread_id="t1",
            rfc_message_id="<g1@example.com>",
            footer_ref="AW-1042-FL1",
            text="Following up on membership FL-5531. Ref AW-1042-FL1",
        )
    )
    family = next(iter(surface.family_tokens))
    payload = dump_surface(surface)

    restored = build_surface("other-passcode")
    load_surface(restored, payload)

    assert restored.demo_passcode == "other-passcode"
    assert restored.family_tokens[family] == surface.demo_case_id
    assert restored.cases[surface.demo_case_id].family_choice == "ask"
    assert restored.cases[surface.demo_case_id].clock_case.clock_offset_s == 14 * 86400
    assert restored.sessions == {"session-fixture"}
    assert restored.mailbox.sent[0].footer_ref == "AW-1042-FL1"
    assert "spoken" not in payload["calls"][next(iter(surface.calls))]
