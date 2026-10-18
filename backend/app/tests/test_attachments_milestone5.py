import hashlib
import io
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings


@pytest.fixture
def client():
    """Synchronous test client configured for Starlette/FastAPI endpoints."""
    return TestClient(app, base_url="http://testserver")


def register_and_login(client: TestClient, username: str, display_name: str) -> dict:
    """Helper to register and login a test user, returning user data with cookies set."""
    res = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "display_name": display_name,
            "password": "Password123!",
        },
    )
    assert res.status_code == 201
    return res.json()


def test_upload_and_download_flow_with_sha256_verification(client: TestClient):
    """Verify end-to-end file upload, metadata generation, and byte-for-byte download."""
    # 1. Register Alice and Bob
    alice = register_and_login(client, "alice_m5_1", "Alice M5")
    alice_cookie = client.cookies.get(settings.SESSION_COOKIE_NAME)

    # Bob
    client.cookies.clear()
    bob = register_and_login(client, "bob_m5_1", "Bob M5")
    bob_cookie = client.cookies.get(settings.SESSION_COOKIE_NAME)

    # Alice creates a direct chat with Bob
    client.cookies.set(settings.SESSION_COOKIE_NAME, alice_cookie)
    conv_res = client.post("/api/conversations/direct", json={"target_user_id": bob["id"]})
    assert conv_res.status_code in (200, 201)
    conv_id = conv_res.json()["id"]

    # 2. Alice uploads a test file
    file_bytes = b"Hello LAN file sharing! This is test content with special chars: 1234567890."
    expected_sha256 = hashlib.sha256(file_bytes).hexdigest()
    filename = "report_test.txt"

    upload_res = client.post(
        f"/api/conversations/{conv_id}/attachments",
        files={"file": (filename, io.BytesIO(file_bytes), "text/plain")},
        data={"client_message_id": "c-file-1"},
    )
    assert upload_res.status_code == 201
    msg_data = upload_res.json()
    assert msg_data["message_type"] == "file"
    assert msg_data["content"] == filename
    assert len(msg_data["attachments"]) == 1

    att = msg_data["attachments"][0]
    assert att["original_filename"] == filename
    assert att["size_bytes"] == len(file_bytes)
    assert att["sha256"] == expected_sha256
    assert att["download_url"] == f"/api/attachments/{att['id']}/download"

    # 3. Bob downloads the file
    client.cookies.set(settings.SESSION_COOKIE_NAME, bob_cookie)
    dl_res = client.get(att["download_url"])
    assert dl_res.status_code == 200
    assert dl_res.content == file_bytes
    assert dl_res.headers.get("X-Content-Type-Options") == "nosniff"
    assert dl_res.headers.get("ETag") == f'"{expected_sha256}"'
    assert f'filename="{filename}"' in dl_res.headers.get("content-disposition", "")


def test_unauthorized_and_removed_members_cannot_download(client: TestClient):
    """Verify that unauthenticated, non-members, and removed members are rejected from downloading attachments."""
    # 1. Register Owner (Alice), Member (Bob), and Stranger (Charlie)
    alice = register_and_login(client, "alice_m5_2", "Alice M5")
    alice_cookie = client.cookies.get(settings.SESSION_COOKIE_NAME)

    client.cookies.clear()
    bob = register_and_login(client, "bob_m5_2", "Bob M5")
    bob_cookie = client.cookies.get(settings.SESSION_COOKIE_NAME)

    client.cookies.clear()
    charlie = register_and_login(client, "charlie_m5_2", "Charlie M5")
    charlie_cookie = client.cookies.get(settings.SESSION_COOKIE_NAME)

    # Alice creates a group with Bob
    client.cookies.set(settings.SESSION_COOKIE_NAME, alice_cookie)
    grp_res = client.post(
        "/api/conversations/groups",
        json={"name": "Secret Project", "member_ids": [bob["id"]]},
    )
    assert grp_res.status_code == 201
    grp_id = grp_res.json()["id"]

    # Alice uploads a file to the group
    file_bytes = b"Top secret corporate budget data."
    upload_res = client.post(
        f"/api/conversations/{grp_id}/attachments",
        files={"file": ("secret_budget.pdf", io.BytesIO(file_bytes), "application/pdf")},
    )
    assert upload_res.status_code == 201
    att_id = upload_res.json()["attachments"][0]["id"]
    download_url = f"/api/attachments/{att_id}/download"

    # 2. Unauthenticated user gets 401
    client.cookies.clear()
    res_unauth = client.get(download_url)
    assert res_unauth.status_code == 401

    # 3. Stranger (Charlie, not a member) gets 403 CONVERSATION_ACCESS_DENIED
    client.cookies.set(settings.SESSION_COOKIE_NAME, charlie_cookie)
    res_stranger = client.get(download_url)
    assert res_stranger.status_code == 403
    assert res_stranger.json()["error"]["code"] == "CONVERSATION_ACCESS_DENIED"

    # 4. Bob downloads successfully while active member
    client.cookies.set(settings.SESSION_COOKIE_NAME, bob_cookie)
    res_bob_active = client.get(download_url)
    assert res_bob_active.status_code == 200
    assert res_bob_active.content == file_bytes

    # 5. Alice removes Bob from the group
    client.cookies.set(settings.SESSION_COOKIE_NAME, alice_cookie)
    del_member_res = client.delete(f"/api/conversations/{grp_id}/members/{bob['id']}")
    assert del_member_res.status_code == 200

    # 6. Bob tries to download again -> gets 403 CONVERSATION_ACCESS_DENIED
    client.cookies.set(settings.SESSION_COOKIE_NAME, bob_cookie)
    res_bob_removed = client.get(download_url)
    assert res_bob_removed.status_code == 403
    assert res_bob_removed.json()["error"]["code"] == "CONVERSATION_ACCESS_DENIED"


def test_path_traversal_sanitization_and_isolation(client: TestClient):
    """Verify that malicious path-traversal filenames are neutralized and stored securely."""
    alice = register_and_login(client, "alice_m5_3", "Alice M5")

    # Direct conversation with self is rejected, so create group
    grp_res = client.post(
        "/api/conversations/groups",
        json={"name": "Traversal Test Group", "member_ids": []},
    )
    assert grp_res.status_code == 201
    grp_id = grp_res.json()["id"]

    # Malicious filename attempting path traversal
    evil_filename = "../../../../../etc/passwd"
    file_bytes = b"root:x:0:0:root:/root:/bin/bash"

    upload_res = client.post(
        f"/api/conversations/{grp_id}/attachments",
        files={"file": (evil_filename, io.BytesIO(file_bytes), "text/plain")},
    )
    assert upload_res.status_code == 201
    msg_data = upload_res.json()
    att = msg_data["attachments"][0]

    # Filename must be sanitized to purely 'passwd'
    assert att["original_filename"] == "passwd"
    assert ".." not in att["original_filename"]
    assert "/" not in att["original_filename"]

    # Verify download succeeds with safe filename
    dl_res = client.get(att["download_url"])
    assert dl_res.status_code == 200
    assert dl_res.content == file_bytes
    assert 'filename="passwd"' in dl_res.headers.get("content-disposition", "")


def test_empty_and_oversized_file_rejections(client: TestClient, monkeypatch):
    """Verify that empty uploads and files exceeding MAX_UPLOAD_SIZE_BYTES are rejected safely."""
    alice = register_and_login(client, "alice_m5_4", "Alice M5")

    grp_res = client.post(
        "/api/conversations/groups",
        json={"name": "Size Limit Group", "member_ids": []},
    )
    grp_id = grp_res.json()["id"]

    # 1. Empty file rejection
    empty_res = client.post(
        f"/api/conversations/{grp_id}/attachments",
        files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")},
    )
    assert empty_res.status_code == 400
    assert empty_res.json()["error"]["code"] == "EMPTY_FILE"

    # 2. Oversized file rejection
    # Set MAX_UPLOAD_SIZE_BYTES to 1024 bytes (1 KB) for fast test execution
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_BYTES", 1024)

    oversized_bytes = b"X" * 2048  # 2 KB > 1 KB limit
    over_res = client.post(
        f"/api/conversations/{grp_id}/attachments",
        files={"file": ("huge.dat", io.BytesIO(oversized_bytes), "application/octet-stream")},
    )
    assert over_res.status_code == 413
    assert over_res.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_non_member_cannot_upload_attachment(client: TestClient):
    """Verify that a user who is not a member of a conversation cannot upload files into it."""
    alice = register_and_login(client, "alice_m5_5", "Alice M5")
    alice_cookie = client.cookies.get(settings.SESSION_COOKIE_NAME)

    client.cookies.clear()
    bob = register_and_login(client, "bob_m5_5", "Bob M5")
    bob_cookie = client.cookies.get(settings.SESSION_COOKIE_NAME)

    # Alice creates a private group with no other members
    client.cookies.set(settings.SESSION_COOKIE_NAME, alice_cookie)
    grp_res = client.post(
        "/api/conversations/groups",
        json={"name": "Alice Private Solo", "member_ids": []},
    )
    grp_id = grp_res.json()["id"]

    # Bob attempts to upload an attachment to Alice's conversation
    client.cookies.set(settings.SESSION_COOKIE_NAME, bob_cookie)
    upload_res = client.post(
        f"/api/conversations/{grp_id}/attachments",
        files={"file": ("injected.txt", io.BytesIO(b"Injected payload"), "text/plain")},
    )
    assert upload_res.status_code == 403
    assert upload_res.json()["error"]["code"] == "CONVERSATION_ACCESS_DENIED"


def test_file_message_delivered_via_websocket(client: TestClient):
    """Verify that uploading an attachment broadcasts message.created with attachment metadata to online WebSocket peers."""
    alice = register_and_login(client, "alice_m5_ws", "Alice WS")
    alice_cookie = client.cookies.get(settings.SESSION_COOKIE_NAME)

    client.cookies.clear()
    bob = register_and_login(client, "bob_m5_ws", "Bob WS")
    bob_cookie = client.cookies.get(settings.SESSION_COOKIE_NAME)

    # Direct chat
    client.cookies.set(settings.SESSION_COOKIE_NAME, alice_cookie)
    conv_res = client.post("/api/conversations/direct", json={"target_user_id": bob["id"]})
    conv_id = conv_res.json()["id"]

    # Bob connects to WebSocket
    client.cookies.set(settings.SESSION_COOKIE_NAME, bob_cookie)
    with client.websocket_connect("/ws") as ws_bob:
        # Initial presence handshake
        ready_evt = ws_bob.receive_json()
        assert ready_evt["type"] == "connection.ready"
        pres_evt = ws_bob.receive_json()
        assert pres_evt["type"] == "presence.snapshot"

        # Alice uploads a file via HTTP
        client.cookies.set(settings.SESSION_COOKIE_NAME, alice_cookie)
        file_bytes = b"Shared document over LAN."
        upload_res = client.post(
            f"/api/conversations/{conv_id}/attachments",
            files={"file": ("shared_doc.txt", io.BytesIO(file_bytes), "text/plain")},
        )
        assert upload_res.status_code == 201

        # Bob receives message.created event via WebSocket
        ws_msg = ws_bob.receive_json()
        assert ws_msg["type"] == "message.created"
        payload = ws_msg["payload"]
        assert payload["conversation_id"] == conv_id
        assert payload["message_type"] == "file"
        assert payload["content"] == "shared_doc.txt"
        assert len(payload["attachments"]) == 1
        assert payload["attachments"][0]["original_filename"] == "shared_doc.txt"
        assert payload["attachments"][0]["download_url"].startswith("/api/attachments/")
