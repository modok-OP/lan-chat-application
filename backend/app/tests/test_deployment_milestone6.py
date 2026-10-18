import ipaddress
import pytest
from httpx import AsyncClient

from app.core.network import get_lan_ips


@pytest.mark.asyncio
async def test_health_check_includes_lan_ips(async_client: AsyncClient):
    """Verify that /api/health includes discovered LAN IPs for network diagnostics."""
    response = await async_client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert "lan_ips" in data
    assert isinstance(data["lan_ips"], list)
    for ip in data["lan_ips"]:
        # Verify each discovered IP is a valid IPv4 address and non-loopback
        ip_obj = ipaddress.ip_address(ip)
        assert ip_obj.version == 4
        assert not ip_obj.is_loopback


def test_get_lan_ips_utility():
    """Verify get_lan_ips returns a list of unique IPv4 addresses without loopbacks."""
    ips = get_lan_ips()
    assert isinstance(ips, list)
    assert len(ips) == len(set(ips))  # No duplicates
    for ip in ips:
        ip_obj = ipaddress.ip_address(ip)
        assert ip_obj.version == 4
        assert not ip_obj.is_loopback


@pytest.mark.asyncio
async def test_single_origin_spa_serving(async_client: AsyncClient):
    """Verify that root / serves compiled SPA index.html with 0 external CDN dependencies."""
    response = await async_client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    content = response.text
    assert '<div id="root">' in content
    assert "LAN Chat Application" in content
    # Offline verification: No external Google Fonts, unpkg, cdnjs, or cdn.jsdelivr
    assert "fonts.googleapis.com" not in content
    assert "cdnjs.cloudflare.com" not in content
    assert "unpkg.com" not in content


@pytest.mark.asyncio
async def test_spa_client_side_routing_fallback(async_client: AsyncClient):
    """Verify that deep client-side routes (e.g. /conversations/abc) fall back to index.html."""
    response = await async_client.get("/conversations/abc")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert '<div id="root">' in response.text


@pytest.mark.asyncio
async def test_spa_static_files(async_client: AsyncClient):
    """Verify that static files like favicon.svg are served with proper content types."""
    response = await async_client.get("/favicon.svg")
    assert response.status_code == 200
    assert "image/svg+xml" in response.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_api_404_not_intercepted_by_spa(async_client: AsyncClient):
    """Verify that /api/... 404s return JSON error envelopes and are NOT intercepted by SPA."""
    response = await async_client.get("/api/unknown_resource_xyz")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "NOT_FOUND"
