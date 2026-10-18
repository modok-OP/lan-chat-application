import pytest
from httpx import AsyncClient
from app.core.config import settings


async def create_authenticated_user(async_client: AsyncClient, username: str) -> dict:
    """Helper to register and return cookies for an authenticated user."""
    res = await async_client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": "Password123!",
            "display_name": f"{username.capitalize()} User",
        },
    )
    assert res.status_code == 201
    user_data = res.json()
    token = res.cookies.get(settings.SESSION_COOKIE_NAME)
    headers = {"Cookie": f"{settings.SESSION_COOKIE_NAME}={token}"}
    return {"user": user_data, "headers": headers}


@pytest.mark.asyncio
async def test_user_search_and_exclusion(async_client: AsyncClient):
    """User search returns active users matching query and excludes the caller."""
    u1 = await create_authenticated_user(async_client, "searcher1")
    u2 = await create_authenticated_user(async_client, "target_find_me")
    u3 = await create_authenticated_user(async_client, "other_person")

    # Search without query
    res = await async_client.get("/api/users", headers=u1["headers"])
    assert res.status_code == 200
    users = res.json()
    user_ids = [u["id"] for u in users]
    assert u1["user"]["id"] not in user_ids
    assert u2["user"]["id"] in user_ids

    # Search with query
    query_res = await async_client.get("/api/users?search=find_me", headers=u1["headers"])
    assert query_res.status_code == 200
    results = query_res.json()
    assert len(results) == 1
    assert results[0]["username"] == "target_find_me"


@pytest.mark.asyncio
async def test_direct_conversation_uniqueness(async_client: AsyncClient):
    """Direct conversation creation is idempotent and never duplicates for the same pair."""
    u1 = await create_authenticated_user(async_client, "direct_user_a")
    u2 = await create_authenticated_user(async_client, "direct_user_b")

    # User A creates direct chat with User B
    res_a = await async_client.post(
        "/api/conversations/direct",
        json={"target_user_id": u2["user"]["id"]},
        headers=u1["headers"],
    )
    assert res_a.status_code == 200
    conv_a = res_a.json()
    assert conv_a["type"] == "direct"
    assert len(conv_a["members"]) == 2

    # User B creates direct chat with User A
    res_b = await async_client.post(
        "/api/conversations/direct",
        json={"target_user_id": u1["user"]["id"]},
        headers=u2["headers"],
    )
    assert res_b.status_code == 200
    conv_b = res_b.json()

    # Must be the exact same conversation ID
    assert conv_a["id"] == conv_b["id"]


@pytest.mark.asyncio
async def test_cannot_direct_chat_self(async_client: AsyncClient):
    """Attempting to direct chat with oneself returns 400 Bad Request."""
    u1 = await create_authenticated_user(async_client, "self_chatter")
    res = await async_client.post(
        "/api/conversations/direct",
        json={"target_user_id": u1["user"]["id"]},
        headers=u1["headers"],
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_unrelated_user_cannot_access_direct_chat(async_client: AsyncClient):
    """A third user cannot view or access another pair's direct conversation."""
    u1 = await create_authenticated_user(async_client, "secret_a")
    u2 = await create_authenticated_user(async_client, "secret_b")
    intruder = await create_authenticated_user(async_client, "intruder_c")

    create_res = await async_client.post(
        "/api/conversations/direct",
        json={"target_user_id": u2["user"]["id"]},
        headers=u1["headers"],
    )
    conv_id = create_res.json()["id"]

    # Intruder tries to fetch conversation details
    intruder_res = await async_client.get(
        f"/api/conversations/{conv_id}",
        headers=intruder["headers"],
    )
    assert intruder_res.status_code == 403
    assert intruder_res.json()["error"]["code"] == "CONVERSATION_ACCESS_DENIED"


@pytest.mark.asyncio
async def test_group_lifecycle_and_roles(async_client: AsyncClient):
    """Test group creation, roles, renaming permissions, and membership changes."""
    owner = await create_authenticated_user(async_client, "group_owner")
    member = await create_authenticated_user(async_client, "group_member")
    outsider = await create_authenticated_user(async_client, "group_outsider")

    # 1. Create group
    create_res = await async_client.post(
        "/api/conversations/groups",
        json={
            "name": "Design Team",
            "member_ids": [member["user"]["id"]],
        },
        headers=owner["headers"],
    )
    assert create_res.status_code == 201
    group_data = create_res.json()
    conv_id = group_data["id"]
    assert group_data["name"] == "Design Team"

    # Check roles
    members_map = {m["user_id"]: m["role"] for m in group_data["members"]}
    assert members_map[owner["user"]["id"]] == "owner"
    assert members_map[member["user"]["id"]] == "member"

    # 2. Rename group by regular member must fail
    fail_rename = await async_client.patch(
        f"/api/conversations/{conv_id}",
        json={"name": "Hacked Name"},
        headers=member["headers"],
    )
    assert fail_rename.status_code == 403

    # 3. Rename group by owner must succeed
    ok_rename = await async_client.patch(
        f"/api/conversations/{conv_id}",
        json={"name": "Engineering Team"},
        headers=owner["headers"],
    )
    assert ok_rename.status_code == 200
    assert ok_rename.json()["name"] == "Engineering Team"

    # 4. Add outsider by owner
    add_res = await async_client.post(
        f"/api/conversations/{conv_id}/members",
        json={"user_id": outsider["user"]["id"], "role": "member"},
        headers=owner["headers"],
    )
    assert add_res.status_code == 200
    assert add_res.json()["user_id"] == outsider["user"]["id"]

    # Outsider can now read details
    can_read = await async_client.get(f"/api/conversations/{conv_id}", headers=outsider["headers"])
    assert can_read.status_code == 200

    # 5. Remove member by owner
    remove_res = await async_client.delete(
        f"/api/conversations/{conv_id}/members/{outsider['user']['id']}",
        headers=owner["headers"],
    )
    assert remove_res.status_code == 200

    # Removed member can no longer read details
    cannot_read = await async_client.get(f"/api/conversations/{conv_id}", headers=outsider["headers"])
    assert cannot_read.status_code == 403

    # 6. Cannot remove group owner
    cannot_remove_owner = await async_client.delete(
        f"/api/conversations/{conv_id}/members/{owner['user']['id']}",
        headers=owner["headers"],
    )
    assert cannot_remove_owner.status_code == 403


@pytest.mark.asyncio
async def test_paginated_message_history(async_client: AsyncClient):
    """Test message posting, authorization, and cursor-based pagination."""
    u1 = await create_authenticated_user(async_client, "msg_user_a")
    u2 = await create_authenticated_user(async_client, "msg_user_b")
    outsider = await create_authenticated_user(async_client, "msg_outsider")

    conv_res = await async_client.post(
        "/api/conversations/direct",
        json={"target_user_id": u2["user"]["id"]},
        headers=u1["headers"],
    )
    conv_id = conv_res.json()["id"]

    # Outsider cannot post to this conversation
    fail_post = await async_client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "Sneaky message"},
        headers=outsider["headers"],
    )
    assert fail_post.status_code == 403

    # Seed 15 messages
    for i in range(1, 16):
        await async_client.post(
            f"/api/conversations/{conv_id}/messages",
            json={"content": f"Message number {i}"},
            headers=u1["headers"],
        )

    # Fetch page 1 (limit 10)
    page1 = await async_client.get(
        f"/api/conversations/{conv_id}/messages?limit=10",
        headers=u2["headers"],
    )
    assert page1.status_code == 200
    p1_data = page1.json()
    assert len(p1_data["messages"]) == 10
    assert p1_data["has_more"] is True
    assert p1_data["oldest_id"] is not None

    # Oldest message in page 1 should be message 6 (since 6..15 is 10 messages)
    assert p1_data["messages"][0]["content"] == "Message number 6"
    assert p1_data["messages"][-1]["content"] == "Message number 15"

    # Fetch page 2 using before=<oldest_id>
    page2 = await async_client.get(
        f"/api/conversations/{conv_id}/messages?before={p1_data['oldest_id']}&limit=10",
        headers=u2["headers"],
    )
    assert page2.status_code == 200
    p2_data = page2.json()
    assert len(p2_data["messages"]) == 5
    assert p2_data["has_more"] is False
    assert p2_data["messages"][0]["content"] == "Message number 1"
    assert p2_data["messages"][-1]["content"] == "Message number 5"


@pytest.mark.asyncio
async def test_message_idempotency_retry(async_client: AsyncClient):
    """Submitting a message with an identical client_message_id returns the existing record."""
    u1 = await create_authenticated_user(async_client, "idemp_a")
    u2 = await create_authenticated_user(async_client, "idemp_b")

    conv_res = await async_client.post(
        "/api/conversations/direct",
        json={"target_user_id": u2["user"]["id"]},
        headers=u1["headers"],
    )
    conv_id = conv_res.json()["id"]

    # First send
    send1 = await async_client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "Network timeout test", "client_message_id": "retry-key-001"},
        headers=u1["headers"],
    )
    assert send1.status_code == 201
    msg1 = send1.json()

    # Retry send with same client_message_id
    send2 = await async_client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "Network timeout test", "client_message_id": "retry-key-001"},
        headers=u1["headers"],
    )
    assert send2.status_code in (200, 201)
    msg2 = send2.json()

    assert msg1["id"] == msg2["id"]
