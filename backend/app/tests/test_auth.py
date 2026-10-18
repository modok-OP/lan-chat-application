import pytest
from httpx import AsyncClient
from sqlalchemy import select
from app.db.models import User
from app.db.session import async_session_maker
from app.core.config import settings


@pytest.mark.asyncio
async def test_register_success(async_client: AsyncClient):
    """Register a new unique user and verify session cookie and response."""
    payload = {
        "username": "alice",
        "password": "Password123!",
        "display_name": "Alice Wonderland",
    }
    response = await async_client.post("/api/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "alice"
    assert data["display_name"] == "Alice Wonderland"
    assert data["role"] == "user"
    assert "password" not in data
    assert "password_hash" not in data

    # Verify session cookie was set
    cookie_header = response.headers.get("set-cookie", "")
    assert settings.SESSION_COOKIE_NAME in cookie_header


@pytest.mark.asyncio
async def test_password_not_stored_in_plaintext():
    """Verify that user passwords in the database are hashed with Argon2."""
    async with async_session_maker() as session:
        stmt = select(User).where(User.username == "alice")
        user = (await session.execute(stmt)).scalar_one_or_none()
        assert user is not None
        assert user.password_hash != "Password123!"
        assert user.password_hash.startswith("$argon2")


@pytest.mark.asyncio
async def test_duplicate_username_rejected(async_client: AsyncClient):
    """Attempting to register an existing username (case-insensitive) must return 409."""
    payload = {
        "username": "ALICE",
        "password": "AnotherPassword456!",
        "display_name": "Alice Duplicate",
    }
    response = await async_client.post("/api/auth/register", json=payload)
    assert response.status_code == 409
    data = response.json()
    assert data["error"]["code"] == "USERNAME_ALREADY_EXISTS"


@pytest.mark.asyncio
async def test_registration_validation_rules(async_client: AsyncClient):
    """Invalid usernames or short passwords must be rejected with 422."""
    # Special characters in username
    bad_user = await async_client.post(
        "/api/auth/register",
        json={"username": "user!@#$", "password": "ValidPassword123"},
    )
    assert bad_user.status_code == 422

    # Password too short (<8 chars)
    short_pass = await async_client.post(
        "/api/auth/register",
        json={"username": "valid_user", "password": "123"},
    )
    assert short_pass.status_code == 422


@pytest.mark.asyncio
async def test_unauthenticated_protected_endpoint_fails(async_client: AsyncClient):
    """Accessing /api/me without a session cookie must return 401 Unauthorized."""
    response = await async_client.get("/api/me")
    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_login_success(async_client: AsyncClient):
    """Login with valid credentials returns user profile and sets session cookie."""
    # Register bob first
    await async_client.post(
        "/api/auth/register",
        json={"username": "bob", "password": "BobSecretPassword99"},
    )

    # Login
    response = await async_client.post(
        "/api/auth/login",
        json={"username": "bob", "password": "BobSecretPassword99"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "bob"
    assert settings.SESSION_COOKIE_NAME in response.headers.get("set-cookie", "")


@pytest.mark.asyncio
async def test_login_invalid_password(async_client: AsyncClient):
    """Login with wrong password fails with 401 and generic message."""
    response = await async_client.post(
        "/api/auth/login",
        json={"username": "bob", "password": "WrongPassword!"},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == "INVALID_CREDENTIALS"
    assert "set-cookie" not in response.headers


@pytest.mark.asyncio
async def test_login_nonexistent_user(async_client: AsyncClient):
    """Login with non-existent username fails with identical generic 401 message."""
    response = await async_client.post(
        "/api/auth/login",
        json={"username": "ghost_user", "password": "SomePassword123"},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_session_lifecycle_and_logout(async_client: AsyncClient):
    """Verify login -> /api/me -> logout -> /api/me fails."""
    # Register charlie
    reg_res = await async_client.post(
        "/api/auth/register",
        json={"username": "charlie", "password": "CharliePassword77", "display_name": "Charlie C."},
    )
    assert reg_res.status_code == 201

    # Extract session cookie from registration
    raw_cookie = reg_res.cookies.get(settings.SESSION_COOKIE_NAME)
    assert raw_cookie is not None
    auth_headers = {"Cookie": f"{settings.SESSION_COOKIE_NAME}={raw_cookie}"}

    # Access /api/me with session cookie
    me_res = await async_client.get("/api/me", headers=auth_headers)
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["username"] == "charlie"
    assert me_data["display_name"] == "Charlie C."

    # Logout
    logout_res = await async_client.post("/api/auth/logout", headers=auth_headers)
    assert logout_res.status_code == 200
    assert logout_res.json()["message"] == "Logged out successfully"

    # Subsequent /api/me request with old cookie must fail with 401
    after_logout_res = await async_client.get("/api/me", headers=auth_headers)
    assert after_logout_res.status_code == 401
