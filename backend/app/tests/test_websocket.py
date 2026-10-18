import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from app.main import app
from app.core.config import settings
from app.tests.test_conversations import create_authenticated_user


def test_unauthenticated_websocket_connection_rejected():
    """Connecting to /ws without a session cookie is rejected with policy violation (1008)."""
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws"):
            pass
    assert exc_info.value.code == 1008


def test_authenticated_websocket_handshake_and_presence():
    """An authenticated user receives connection.ready and presence.snapshot upon connect."""
    client = TestClient(app)
    # Register user via synchronous test client helper
    reg_res = client.post(
        "/api/auth/register",
        json={"username": "ws_user1", "password": "Password123!", "display_name": "WS User 1"},
    )
    assert reg_res.status_code == 201
    user1_id = reg_res.json()["id"]

    cookies = {settings.SESSION_COOKIE_NAME: reg_res.cookies.get(settings.SESSION_COOKIE_NAME)}

    with client.websocket_connect("/ws", cookies=cookies) as ws:
        # 1. Expect connection.ready
        ready_event = ws.receive_json()
        assert ready_event["type"] == "connection.ready"
        assert ready_event["payload"]["user"]["id"] == user1_id

        # 2. Expect presence.snapshot
        snapshot_event = ws.receive_json()
        assert snapshot_event["type"] == "presence.snapshot"
        assert user1_id in snapshot_event["payload"]["online_users"]

        # 3. Test ping-pong
        ws.send_json({"type": "ping", "request_id": "ping-123"})
        pong_event = ws.receive_json()
        assert pong_event["type"] == "pong"
        assert pong_event["request_id"] == "ping-123"


def test_two_clients_live_message_exchange_and_isolation():
    """Verify live message exchange between 2 participants and isolation from non-members.

    1. Alice and Bob are in a conversation.
    2. Charlie is NOT in the conversation.
    3. Alice sends message via WebSocket -> Bob receives live message.
    4. Charlie does NOT receive the message.
    5. Charlie cannot send into the conversation.
    """
    client = TestClient(app)

    # 1. Register Alice, Bob, and Charlie
    r_alice = client.post("/api/auth/register", json={"username": "alice_ws", "password": "Password123!"})
    r_bob = client.post("/api/auth/register", json={"username": "bob_ws", "password": "Password123!"})
    r_charlie = client.post("/api/auth/register", json={"username": "charlie_ws", "password": "Password123!"})

    alice_id = r_alice.json()["id"]
    bob_id = r_bob.json()["id"]
    charlie_id = r_charlie.json()["id"]

    alice_cookies = {settings.SESSION_COOKIE_NAME: r_alice.cookies.get(settings.SESSION_COOKIE_NAME)}
    bob_cookies = {settings.SESSION_COOKIE_NAME: r_bob.cookies.get(settings.SESSION_COOKIE_NAME)}
    charlie_cookies = {settings.SESSION_COOKIE_NAME: r_charlie.cookies.get(settings.SESSION_COOKIE_NAME)}

    # 2. Create direct conversation between Alice and Bob
    conv_res = client.post(
        "/api/conversations/direct",
        json={"target_user_id": bob_id},
        cookies=alice_cookies,
    )
    assert conv_res.status_code == 200
    conv_id = conv_res.json()["id"]

    # 3. Connect Alice and Bob
    with client.websocket_connect("/ws", cookies=alice_cookies) as ws_alice:
        # Drain Alice's initial handshake
        assert ws_alice.receive_json()["type"] == "connection.ready"
        assert ws_alice.receive_json()["type"] == "presence.snapshot"

        with client.websocket_connect("/ws", cookies=bob_cookies) as ws_bob:
            # Drain Bob's initial handshake
            assert ws_bob.receive_json()["type"] == "connection.ready"
            assert ws_bob.receive_json()["type"] == "presence.snapshot"

            # Alice should receive presence.changed (Bob came online)
            presence_event = ws_alice.receive_json()
            assert presence_event["type"] == "presence.changed"
            assert presence_event["payload"]["user_id"] == bob_id
            assert presence_event["payload"]["status"] == "online"

            with client.websocket_connect("/ws", cookies=charlie_cookies) as ws_charlie:
                # Drain Charlie's initial handshake
                assert ws_charlie.receive_json()["type"] == "connection.ready"
                assert ws_charlie.receive_json()["type"] == "presence.snapshot"

                # Drain Charlie online event from Alice and Bob
                _ = ws_alice.receive_json()
                _ = ws_bob.receive_json()

                # 4. Alice sends message via WebSocket
                ws_alice.send_json({
                    "type": "message.send",
                    "request_id": "req-alice-01",
                    "payload": {
                        "conversation_id": conv_id,
                        "content": "Live greetings from Alice over WebSocket!",
                        "client_message_id": "c-uuid-1",
                    },
                })

                # Alice receives message.ack
                ack = ws_alice.receive_json()
                assert ack["type"] == "message.ack"
                assert ack["request_id"] == "req-alice-01"
                assert ack["payload"]["conversation_id"] == conv_id

                # Alice and Bob both receive message.created (as active members)
                alice_created = ws_alice.receive_json()
                assert alice_created["type"] == "message.created"
                assert alice_created["payload"]["content"] == "Live greetings from Alice over WebSocket!"

                bob_created = ws_bob.receive_json()
                assert bob_created["type"] == "message.created"
                assert bob_created["payload"]["content"] == "Live greetings from Alice over WebSocket!"
                assert bob_created["payload"]["sender"]["username"] == "alice_ws"

                # 5. Charlie (unauthorized non-member) tries to send into Alice & Bob's conversation
                ws_charlie.send_json({
                    "type": "message.send",
                    "request_id": "req-charlie-hack",
                    "payload": {
                        "conversation_id": conv_id,
                        "content": "Intruder attempting to inject message",
                    },
                })

                charlie_err = ws_charlie.receive_json()
                assert charlie_err["type"] == "error"
                assert charlie_err["request_id"] == "req-charlie-hack"
                assert charlie_err["payload"]["code"] == "CONVERSATION_ACCESS_DENIED"


def test_idempotent_retry_over_websocket():
    """Sending an identical client_message_id returns ack with same message ID without duplicating."""
    client = TestClient(app)

    r_alice = client.post("/api/auth/register", json={"username": "ws_idemp_a", "password": "Password123!"})
    r_bob = client.post("/api/auth/register", json={"username": "ws_idemp_b", "password": "Password123!"})
    alice_cookies = {settings.SESSION_COOKIE_NAME: r_alice.cookies.get(settings.SESSION_COOKIE_NAME)}

    conv_res = client.post(
        "/api/conversations/direct",
        json={"target_user_id": r_bob.json()["id"]},
        cookies=alice_cookies,
    )
    conv_id = conv_res.json()["id"]

    with client.websocket_connect("/ws", cookies=alice_cookies) as ws:
        _ = ws.receive_json()  # ready
        _ = ws.receive_json()  # snapshot

        # First send
        ws.send_json({
            "type": "message.send",
            "request_id": "try-1",
            "payload": {
                "conversation_id": conv_id,
                "content": "Idempotency test payload",
                "client_message_id": "ws-idemp-key-555",
            },
        })
        ack1 = ws.receive_json()
        assert ack1["type"] == "message.ack"
        msg_id1 = ack1["payload"]["message_id"]
        _ = ws.receive_json()  # message.created

        # Retry with same client_message_id
        ws.send_json({
            "type": "message.send",
            "request_id": "try-2",
            "payload": {
                "conversation_id": conv_id,
                "content": "Idempotency test payload",
                "client_message_id": "ws-idemp-key-555",
            },
        })
        ack2 = ws.receive_json()
        assert ack2["type"] == "message.ack"
        assert ack2["payload"]["message_id"] == msg_id1


def test_typing_indicators_and_read_receipts():
    """Verify typing.start / typing.stop and message.read over WebSocket."""
    client = TestClient(app)

    r_alice = client.post("/api/auth/register", json={"username": "alice_ws_t", "password": "Password123!"})
    r_bob = client.post("/api/auth/register", json={"username": "bob_ws_t", "password": "Password123!"})

    alice_id = r_alice.json()["id"]
    bob_id = r_bob.json()["id"]

    alice_cookies = {settings.SESSION_COOKIE_NAME: r_alice.cookies.get(settings.SESSION_COOKIE_NAME)}
    bob_cookies = {settings.SESSION_COOKIE_NAME: r_bob.cookies.get(settings.SESSION_COOKIE_NAME)}

    conv_res = client.post(
        "/api/conversations/direct",
        json={"target_user_id": bob_id},
        cookies=alice_cookies,
    )
    conv_id = conv_res.json()["id"]

    with client.websocket_connect("/ws", cookies=alice_cookies) as ws_alice:
        _ = ws_alice.receive_json()  # ready
        _ = ws_alice.receive_json()  # snapshot

        with client.websocket_connect("/ws", cookies=bob_cookies) as ws_bob:
            _ = ws_bob.receive_json()  # ready
            _ = ws_bob.receive_json()  # snapshot

            _ = ws_alice.receive_json()  # Bob presence.changed

            # 1. Alice sends typing.start
            ws_alice.send_json({
                "type": "typing.start",
                "payload": {"conversation_id": conv_id},
            })
            ws_alice.send_json({"type": "ping", "request_id": "sync-1"})
            assert ws_alice.receive_json()["type"] == "pong"

            typing_event = ws_bob.receive_json()
            assert typing_event["type"] == "typing.updated"
            assert typing_event["payload"]["conversation_id"] == conv_id
            assert typing_event["payload"]["user_id"] == alice_id
            assert typing_event["payload"]["is_typing"] is True

            # 2. Alice sends typing.stop
            ws_alice.send_json({
                "type": "typing.stop",
                "payload": {"conversation_id": conv_id},
            })
            ws_alice.send_json({"type": "ping", "request_id": "sync-2"})
            assert ws_alice.receive_json()["type"] == "pong"

            stop_event = ws_bob.receive_json()
            assert stop_event["type"] == "typing.updated"
            assert stop_event["payload"]["is_typing"] is False

            # 3. Alice sends message
            ws_alice.send_json({
                "type": "message.send",
                "request_id": "req-m7-msg",
                "payload": {"conversation_id": conv_id, "content": "Hello Bob from M7!"},
            })
            ack = ws_alice.receive_json()
            assert ack["type"] == "message.ack"
            msg_id = ack["payload"]["message_id"]

            _ = ws_alice.receive_json()  # message.created for Alice
            bob_created = ws_bob.receive_json()  # message.created for Bob
            assert bob_created["type"] == "message.created"
            assert bob_created["payload"]["message_id"] == msg_id

            # 4. Bob sends message.read
            ws_bob.send_json({
                "type": "message.read",
                "request_id": "read-ack-1",
                "payload": {"conversation_id": conv_id, "last_read_message_id": msg_id},
            })

            read_ack = ws_bob.receive_json()
            assert read_ack["type"] == "message.read.ack"
            assert read_ack["payload"]["last_read_message_id"] == msg_id

            # Alice receives message.read.updated
            alice_read = ws_alice.receive_json()
            assert alice_read["type"] == "message.read.updated"
            assert alice_read["payload"]["conversation_id"] == conv_id
            assert alice_read["payload"]["user_id"] == bob_id
            assert alice_read["payload"]["last_read_message_id"] == msg_id

