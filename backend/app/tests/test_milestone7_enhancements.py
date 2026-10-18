import pytest
from starlette.testclient import TestClient
from app.main import app
from app.core.config import settings


def register_user(client: TestClient, username: str, display_name: str):
    res = client.post(
        "/api/auth/register",
        json={"username": username, "password": "Password123!", "display_name": display_name},
    )
    assert res.status_code == 201
    return res.json()["id"], {settings.SESSION_COOKIE_NAME: res.cookies.get(settings.SESSION_COOKIE_NAME)}


def test_unread_counts_and_mark_read_via_http():
    """Verify unread counts calculation and mark-as-read REST endpoint."""
    client = TestClient(app)
    alice_id, alice_cookies = register_user(client, "alice_m7", "Alice M7")
    bob_id, bob_cookies = register_user(client, "bob_m7", "Bob M7")

    # 1. Create direct conversation
    conv_res = client.post(
        "/api/conversations/direct",
        json={"target_user_id": bob_id},
        cookies=alice_cookies,
    )
    assert conv_res.status_code == 200
    conv_id = conv_res.json()["id"]

    # 2. Both initially have 0 unread
    res_a = client.get("/api/conversations", cookies=alice_cookies)
    assert res_a.status_code == 200
    assert res_a.json()[0]["unread_count"] == 0

    res_b = client.get("/api/conversations", cookies=bob_cookies)
    assert res_b.status_code == 200
    assert res_b.json()[0]["unread_count"] == 0

    # 3. Alice posts 2 messages
    msg1 = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "Message 1 from Alice"},
        cookies=alice_cookies,
    )
    assert msg1.status_code == 201

    msg2 = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "Message 2 from Alice"},
        cookies=alice_cookies,
    )
    assert msg2.status_code == 201
    msg2_id = msg2.json()["id"]

    # 4. Check unread counts: Alice should have 0 (own messages), Bob should have 2
    res_a2 = client.get("/api/conversations", cookies=alice_cookies)
    assert res_a2.json()[0]["unread_count"] == 0

    res_b2 = client.get("/api/conversations", cookies=bob_cookies)
    assert res_b2.json()[0]["unread_count"] == 2

    # 5. Bob marks conversation as read up to msg2_id
    read_res = client.post(
        f"/api/conversations/{conv_id}/read",
        json={"last_read_message_id": msg2_id},
        cookies=bob_cookies,
    )
    assert read_res.status_code == 200
    assert read_res.json()["last_read_message_id"] == msg2_id
    assert read_res.json()["unread_count"] == 0

    # 6. Verify Bob's unread count is now 0 and member last_read_message_id is updated
    res_b3 = client.get(f"/api/conversations/{conv_id}", cookies=bob_cookies)
    assert res_b3.json()["unread_count"] == 0
    bob_member = next(m for m in res_b3.json()["members"] if m["user_id"] == bob_id)
    assert bob_member["last_read_message_id"] == msg2_id


def test_search_conversation_messages():
    """Verify search within conversation respecting member permissions."""
    client = TestClient(app)
    alice_id, alice_cookies = register_user(client, "alice_s7", "Alice Search")
    bob_id, bob_cookies = register_user(client, "bob_s7", "Bob Search")
    charlie_id, charlie_cookies = register_user(client, "charlie_s7", "Charlie Search")

    # Create direct conversation between Alice and Bob
    conv_res = client.post(
        "/api/conversations/direct",
        json={"target_user_id": bob_id},
        cookies=alice_cookies,
    )
    assert conv_res.status_code == 200
    conv_id = conv_res.json()["id"]

    # Post test messages
    client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "Meeting scheduled for 3pm in the conference room"},
        cookies=alice_cookies,
    )
    client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "Sounds good, I will bring the network architecture report"},
        cookies=bob_cookies,
    )
    client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "Don't forget the HDMI cable"},
        cookies=alice_cookies,
    )

    # 1. Search for "architecture" (Bob - active member)
    res_search1 = client.get(
        f"/api/conversations/{conv_id}/messages/search?q=architecture",
        cookies=bob_cookies,
    )
    assert res_search1.status_code == 200
    data1 = res_search1.json()
    assert data1["total_matches"] == 1
    assert "network architecture report" in data1["messages"][0]["content"]

    # 2. Case-insensitive search: "CONFERENCE" (Alice - active member)
    res_search2 = client.get(
        f"/api/conversations/{conv_id}/messages/search?q=CONFERENCE",
        cookies=alice_cookies,
    )
    assert res_search2.status_code == 200
    data2 = res_search2.json()
    assert data2["total_matches"] == 1
    assert "conference room" in data2["messages"][0]["content"]

    # 3. Search non-existent phrase
    res_search3 = client.get(
        f"/api/conversations/{conv_id}/messages/search?q=quantum_cryptography",
        cookies=bob_cookies,
    )
    assert res_search3.status_code == 200
    assert res_search3.json()["total_matches"] == 0

    # 4. Charlie (non-member) attempts search -> must receive 403 Forbidden
    res_search_unauth = client.get(
        f"/api/conversations/{conv_id}/messages/search?q=meeting",
        cookies=charlie_cookies,
    )
    assert res_search_unauth.status_code == 403


def test_message_replies():
    """Verify posting messages with reply_to_message_id and serializing reply summaries."""
    client = TestClient(app)
    alice_id, alice_cookies = register_user(client, "alice_rep7", "Alice Reply")
    bob_id, bob_cookies = register_user(client, "bob_rep7", "Bob Reply")

    conv_res = client.post(
        "/api/conversations/direct",
        json={"target_user_id": bob_id},
        cookies=alice_cookies,
    )
    assert conv_res.status_code == 200
    conv_id = conv_res.json()["id"]

    # 1. Alice posts root message
    msg1_res = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "What time is the lunch meeting?"},
        cookies=alice_cookies,
    )
    assert msg1_res.status_code == 201
    msg1 = msg1_res.json()
    assert msg1["reply_to_message_id"] is None
    assert msg1["reply_to"] is None

    # 2. Bob replies to Alice's message
    msg2_res = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "content": "It is at 1:00 PM in the cafeteria.",
            "reply_to_message_id": msg1["id"],
        },
        cookies=bob_cookies,
    )
    assert msg2_res.status_code == 201
    msg2 = msg2_res.json()
    assert msg2["reply_to_message_id"] == msg1["id"]
    assert msg2["reply_to"] is not None
    assert msg2["reply_to"]["id"] == msg1["id"]
    assert msg2["reply_to"]["content"] == "What time is the lunch meeting?"
    assert msg2["reply_to"]["sender_username"] == "alice_rep7"

    # 3. Retrieve messages and ensure reply_to is populated
    history_res = client.get(f"/api/conversations/{conv_id}/messages", cookies=alice_cookies)
    assert history_res.status_code == 200
    msgs = history_res.json()["messages"]
    reply_msg = next(m for m in msgs if m["id"] == msg2["id"])
    assert reply_msg["reply_to"] is not None
    assert reply_msg["reply_to"]["id"] == msg1["id"]

    # 4. Reply to invalid/non-existent message id falls back gracefully
    msg3_res = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "content": "Replying to ghost message",
            "reply_to_message_id": 999999,
        },
        cookies=alice_cookies,
    )
    assert msg3_res.status_code == 201
    assert msg3_res.json()["reply_to_message_id"] is None
    assert msg3_res.json()["reply_to"] is None


def test_message_emoji_reactions():
    """Verify toggling emoji reactions, count aggregation, and access control."""
    client = TestClient(app)
    alice_id, alice_cookies = register_user(client, "alice_rx7", "Alice Reactions")
    bob_id, bob_cookies = register_user(client, "bob_rx7", "Bob Reactions")
    charlie_id, charlie_cookies = register_user(client, "charlie_rx7", "Charlie NonMember")

    conv_res = client.post(
        "/api/conversations/direct",
        json={"target_user_id": bob_id},
        cookies=alice_cookies,
    )
    assert conv_res.status_code == 200
    conv_id = conv_res.json()["id"]

    # Alice posts a message
    msg_res = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "Release v1.0 is ready!"},
        cookies=alice_cookies,
    )
    assert msg_res.status_code == 201
    msg_id = msg_res.json()["id"]

    # 1. Bob reacts with 👍
    react1 = client.post(
        f"/api/messages/{msg_id}/reactions",
        json={"emoji": "👍"},
        cookies=bob_cookies,
    )
    assert react1.status_code == 200
    data1 = react1.json()
    assert data1["action"] == "added"
    assert len(data1["reactions"]) == 1
    assert data1["reactions"][0]["emoji"] == "👍"
    assert data1["reactions"][0]["count"] == 1
    assert bob_id in data1["reactions"][0]["user_ids"]
    assert "bob_rx7" in data1["reactions"][0]["usernames"]

    # 2. Alice also reacts with 👍
    react2 = client.post(
        f"/api/messages/{msg_id}/reactions",
        json={"emoji": "👍"},
        cookies=alice_cookies,
    )
    assert react2.status_code == 200
    data2 = react2.json()
    assert data2["action"] == "added"
    assert len(data2["reactions"]) == 1
    assert data2["reactions"][0]["count"] == 2
    assert set(data2["reactions"][0]["user_ids"]) == {bob_id, alice_id}

    # 3. Bob also reacts with 🎉
    react3 = client.post(
        f"/api/messages/{msg_id}/reactions",
        json={"emoji": "🎉"},
        cookies=bob_cookies,
    )
    assert react3.status_code == 200
    data3 = react3.json()
    assert len(data3["reactions"]) == 2

    # 4. Bob toggles 👍 again -> should be removed
    react4 = client.post(
        f"/api/messages/{msg_id}/reactions",
        json={"emoji": "👍"},
        cookies=bob_cookies,
    )
    assert react4.status_code == 200
    data4 = react4.json()
    assert data4["action"] == "removed"
    thumbs = next(r for r in data4["reactions"] if r["emoji"] == "👍")
    assert thumbs["count"] == 1
    assert thumbs["user_ids"] == [alice_id]

    # 5. Fetch message list and verify reactions persist
    fetch_res = client.get(f"/api/conversations/{conv_id}/messages", cookies=alice_cookies)
    assert fetch_res.status_code == 200
    fetched_msg = next(m for m in fetch_res.json()["messages"] if m["id"] == msg_id)
    assert len(fetched_msg["reactions"]) == 2

    # 6. Charlie (non-member) tries to react -> 403 Forbidden
    react_unauth = client.post(
        f"/api/messages/{msg_id}/reactions",
        json={"emoji": "❤️"},
        cookies=charlie_cookies,
    )
    assert react_unauth.status_code == 403

    # 7. Invalid emoji (empty or > 16 chars)
    react_bad = client.post(
        f"/api/messages/{msg_id}/reactions",
        json={"emoji": ""},
        cookies=alice_cookies,
    )
    assert react_bad.status_code in (400, 422)




