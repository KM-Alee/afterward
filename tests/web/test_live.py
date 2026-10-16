"""A published desk event reaches a WebSocket subscriber."""

from tests.web.conftest import login


def test_published_event_reaches_subscriber(client):
    login(client)
    case_id = client.app.state.surface.demo_case_id
    with client.websocket_connect(f"/ws/cases/{case_id}") as socket:
        ready = socket.receive_json()
        assert ready["kind"] == "stream.ready"
        client.app.state.surface.live.publish(
            case_id,
            "reply.checked",
            {"summary": "Northline reply held for review"},
            actor="desk",
        )
        event = socket.receive_json()
    assert event["kind"] == "reply.checked"
    assert event["payload"]["summary"] == "Northline reply held for review"
    assert event["case_id"] == str(case_id)


def test_event_stream_rejects_a_secret_payload(client):
    case_id = client.app.state.surface.demo_case_id
    try:
        client.app.state.surface.live.publish(
            case_id,
            "reply.checked",
            {"token": "hidden"},
        )
    except Exception as exc:
        assert exc.__class__.__name__ == "UnsafeEventPayload"
    else:
        raise AssertionError("secret payload keys must be refused")
