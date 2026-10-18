import pytest
from httpx import AsyncClient
from app.core.security import hash_password, verify_password
from app.db.session import check_database_health


@pytest.mark.asyncio
async def test_health_check_endpoint(async_client: AsyncClient):
    """Verify that the health check endpoint returns 200 and expected status."""
    response = await async_client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert data["app_name"] == "LAN Chat Application"
    assert "version" in data
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_standard_404_error_envelope(async_client: AsyncClient):
    """Verify that unknown routes return the standardized error envelope."""
    response = await async_client.get("/api/nonexistent-route-for-testing")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "NOT_FOUND"
    assert "message" in data["error"]


@pytest.mark.asyncio
async def test_database_direct_connectivity():
    """Verify direct SQLite database connectivity via async connection."""
    is_healthy = await check_database_health()
    assert is_healthy is True


def test_argon2_hashing_works():
    """Verify Argon2 password hashing produces secure non-plaintext hashes and verifies."""
    raw_pass = "SuperSecretPassword123"
    hashed = hash_password(raw_pass)
    assert hashed != raw_pass
    assert hashed.startswith("$argon2")
    assert verify_password(raw_pass, hashed) is True
    assert verify_password("WrongPassword", hashed) is False
