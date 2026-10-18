import pytest
from starlette.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.tests.test_conversations import create_authenticated_user


def make_user(client: TestClient, username: str, display_name: str) -> dict:
    res = client.post(
        "/api/auth/register",
        json={"username": username, "password": "Password123!", "display_name": display_name},
    )
    assert res.status_code == 201
    return {
        "id": res.json()["id"],
        "username": username,
        "display_name": display_name,
        "token": res.cookies.get(settings.SESSION_COOKIE_NAME),
    }


def test_group_roles_and_member_management():
    """Verify role permissions for group administration:
    - Only owner/admin can rename group.
    - Only owner/admin can add members.
    - Admin cannot remove another admin or the owner.
    - Owner can remove admins and members.
    - Removed member cannot post or read history.
    """
    client = TestClient(app)

    # 1. Register Owner (Alice), Member (Bob), Admin (Charlie), and Member2 (Dave)
    alice = make_user(client, "alice_g1", "Alice")
    bob = make_user(client, "bob_g1", "Bob")
    charlie = make_user(client, "charlie_g1", "Charlie")
    dave = make_user(client, "dave_g1", "Dave")

    alice_c = {settings.SESSION_COOKIE_NAME: alice["token"]}
    bob_c = {settings.SESSION_COOKIE_NAME: bob["token"]}
    charlie_c = {settings.SESSION_COOKIE_NAME: charlie["token"]}
    dave_c = {settings.SESSION_COOKIE_NAME: dave["token"]}

    # 2. Alice creates group with Bob as initial member
    cg_res = client.post(
        "/api/conversations/groups",
        json={"name": "Engineering Team", "member_ids": [bob["id"]]},
        cookies=alice_c,
    )
    assert cg_res.status_code == 201
    group_id = cg_res.json()["id"]

    # 3. Bob (regular member) tries to rename group -> rejected 403
    rename_res = client.patch(
        f"/api/conversations/{group_id}",
        json={"name": "Bob's Team"},
        cookies=bob_c,
    )
    assert rename_res.status_code == 403
    assert rename_res.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"

    # 4. Bob tries to add Charlie -> rejected 403
    add_res = client.post(
        f"/api/conversations/{group_id}/members",
        json={"user_id": charlie["id"], "role": "member"},
        cookies=bob_c,
    )
    assert add_res.status_code == 403

    # 5. Alice (owner) adds Charlie as admin -> succeeds
    add_charlie_res = client.post(
        f"/api/conversations/{group_id}/members",
        json={"user_id": charlie["id"], "role": "admin"},
        cookies=alice_c,
    )
    assert add_charlie_res.status_code == 200
    assert add_charlie_res.json()["role"] == "admin"

    # 6. Charlie (admin) renames group -> succeeds
    admin_rename = client.patch(
        f"/api/conversations/{group_id}",
        json={"name": "Core Engineering"},
        cookies=charlie_c,
    )
    assert admin_rename.status_code == 200
    assert admin_rename.json()["name"] == "Core Engineering"

    # 7. Charlie (admin) adds Dave as regular member -> succeeds
    add_dave = client.post(
        f"/api/conversations/{group_id}/members",
        json={"user_id": dave["id"], "role": "member"},
        cookies=charlie_c,
    )
    assert add_dave.status_code == 200

    # 8. Charlie (admin) tries to remove Alice (owner) -> rejected 403
    rm_owner = client.delete(
        f"/api/conversations/{group_id}/members/{alice['id']}",
        cookies=charlie_c,
    )
    assert rm_owner.status_code == 403
    assert "Cannot remove the group owner" in rm_owner.json()["error"]["message"]

    # 9. Alice promotes Dave to admin, and Charlie tries to remove Dave (admin vs admin) -> rejected 403
    _ = client.post(
        f"/api/conversations/{group_id}/members",
        json={"user_id": dave["id"], "role": "admin"},
        cookies=alice_c,
    )
    rm_admin_by_admin = client.delete(
        f"/api/conversations/{group_id}/members/{dave['id']}",
        cookies=charlie_c,
    )
    assert rm_admin_by_admin.status_code == 403
    assert "Only the owner can remove group admins" in rm_admin_by_admin.json()["error"]["message"]

    # 10. Alice (owner) removes Dave -> succeeds
    rm_dave = client.delete(
        f"/api/conversations/{group_id}/members/{dave['id']}",
        cookies=alice_c,
    )
    assert rm_dave.status_code == 200

    # 11. Dave (removed) cannot send messages -> 403
    send_res = client.post(
        f"/api/conversations/{group_id}/messages",
        json={"content": "Can Dave still send?"},
        cookies=dave_c,
    )
    assert send_res.status_code == 403
    assert send_res.json()["error"]["code"] == "CONVERSATION_ACCESS_DENIED"

    # 12. Dave (removed) cannot fetch conversation messages -> 403
    hist_res = client.get(
        f"/api/conversations/{group_id}/messages",
        cookies=dave_c,
    )
    assert hist_res.status_code == 403
    assert hist_res.json()["error"]["code"] == "CONVERSATION_ACCESS_DENIED"

    # 13. System messages exist in message history
    history = client.get(
        f"/api/conversations/{group_id}/messages",
        cookies=alice_c,
    ).json()["messages"]

    system_msgs = [m for m in history if m["message_type"] == "system"]
    assert len(system_msgs) >= 3
    # Check that system messages include display names and actions
    contents = [m["content"] for m in system_msgs]
    assert any("created the group" in c for c in contents)
    assert any("renamed the group" in c for c in contents)
    assert any("removed" in c for c in contents)


def test_owner_transfer_and_leave_rules():
    """Verify owner leave and transfer rules:
    - Owner cannot leave if other members remain.
    - Owner can transfer ownership to another member.
    - Previous owner becomes admin and can then leave.
    """
    client = TestClient(app)

    alice = make_user(client, "alice_own", "Alice")
    bob = make_user(client, "bob_own", "Bob")

    alice_c = {settings.SESSION_COOKIE_NAME: alice["token"]}
    bob_c = {settings.SESSION_COOKIE_NAME: bob["token"]}

    cg_res = client.post(
        "/api/conversations/groups",
        json={"name": "Special Project", "member_ids": [bob["id"]]},
        cookies=alice_c,
    )
    group_id = cg_res.json()["id"]

    # 1. Alice tries to leave while Bob is active -> rejected 403 OWNER_CANNOT_LEAVE
    leave_res = client.post(f"/api/conversations/{group_id}/leave", cookies=alice_c)
    assert leave_res.status_code == 403
    assert leave_res.json()["error"]["code"] == "OWNER_CANNOT_LEAVE"

    # 2. Bob tries to transfer ownership -> rejected 403
    bob_xfer = client.post(
        f"/api/conversations/{group_id}/transfer-ownership",
        json={"new_owner_id": bob["id"]},
        cookies=bob_c,
    )
    assert bob_xfer.status_code == 403

    # 3. Alice transfers ownership to Bob -> succeeds
    xfer_res = client.post(
        f"/api/conversations/{group_id}/transfer-ownership",
        json={"new_owner_id": bob["id"]},
        cookies=alice_c,
    )
    assert xfer_res.status_code == 200
    members = {m["user_id"]: m["role"] for m in xfer_res.json()["members"]}
    assert members[bob["id"]] == "owner"
    assert members[alice["id"]] == "admin"

    # 4. Alice (now admin) can voluntarily leave group -> succeeds
    alice_leave = client.post(f"/api/conversations/{group_id}/leave", cookies=alice_c)
    assert alice_leave.status_code == 200

    # 5. Bob (only remaining member) can now leave or delete
    bob_leave = client.post(f"/api/conversations/{group_id}/leave", cookies=bob_c)
    assert bob_leave.status_code == 200


def test_removed_member_isolated_from_live_websocket():
    """Verify that a removed group member receives no subsequent live WebSocket messages."""
    client = TestClient(app)

    alice = make_user(client, "alice_wsm4", "Alice")
    bob = make_user(client, "bob_wsm4", "Bob")
    charlie = make_user(client, "charlie_wsm4", "Charlie")

    alice_c = {settings.SESSION_COOKIE_NAME: alice["token"]}
    bob_c = {settings.SESSION_COOKIE_NAME: bob["token"]}
    charlie_c = {settings.SESSION_COOKIE_NAME: charlie["token"]}

    cg = client.post(
        "/api/conversations/groups",
        json={"name": "Dev Squad", "member_ids": [bob["id"], charlie["id"]]},
        cookies=alice_c,
    )
    group_id = cg.json()["id"]

    with client.websocket_connect("/ws", cookies=alice_c) as ws_a:
        _ = ws_a.receive_json()  # ready
        _ = ws_a.receive_json()  # snapshot

        with client.websocket_connect("/ws", cookies=bob_c) as ws_b:
            _ = ws_b.receive_json()  # ready
            _ = ws_b.receive_json()  # snapshot
            _ = ws_a.receive_json()  # bob presence

            with client.websocket_connect("/ws", cookies=charlie_c) as ws_c:
                _ = ws_c.receive_json()  # ready
                _ = ws_c.receive_json()  # snapshot
                _ = ws_a.receive_json()  # charlie presence
                _ = ws_b.receive_json()  # charlie presence

                # Alice removes Charlie from the group via HTTP
                rm_res = client.delete(
                    f"/api/conversations/{group_id}/members/{charlie['id']}",
                    cookies=alice_c,
                )
                assert rm_res.status_code == 200

                # All 3 receive conversation.updated
                _ = ws_a.receive_json()
                _ = ws_b.receive_json()
                charlie_update = ws_c.receive_json()
                assert charlie_update["type"] == "conversation.updated"
                assert charlie_update["payload"]["conversation_id"] == group_id

                # Alice and Bob receive the system message for Charlie's removal
                sys_a = ws_a.receive_json()
                assert sys_a["type"] == "message.created"
                assert sys_a["payload"]["message_type"] == "system"
                assert "removed Charlie" in sys_a["payload"]["content"]

                sys_b = ws_b.receive_json()
                assert sys_b["type"] == "message.created"
                assert sys_b["payload"]["message_type"] == "system"

                # Alice now sends a confidential message to the group
                ws_a.send_json({
                    "type": "message.send",
                    "request_id": "req-m4-confidential",
                    "payload": {
                        "conversation_id": group_id,
                        "content": "Secret engineering plan post-removal",
                    },
                })

                # Alice receives ack and message.created
                ack = ws_a.receive_json()
                assert ack["type"] == "message.ack"
                msg_a = ws_a.receive_json()
                assert msg_a["payload"]["content"] == "Secret engineering plan post-removal"

                # Bob receives message.created
                msg_b = ws_b.receive_json()
                assert msg_b["payload"]["content"] == "Secret engineering plan post-removal"

                # Charlie (removed) tries to send into group -> receives CONVERSATION_ACCESS_DENIED
                ws_c.send_json({
                    "type": "message.send",
                    "request_id": "req-c-hacker",
                    "payload": {
                        "conversation_id": group_id,
                        "content": "Can I still post here?",
                    },
                })
                err_c = ws_c.receive_json()
                assert err_c["type"] == "error"
                assert err_c["payload"]["code"] == "CONVERSATION_ACCESS_DENIED"
