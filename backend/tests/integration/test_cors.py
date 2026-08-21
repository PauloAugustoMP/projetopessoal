"""The desktop app runs in a webview, so cross-origin access must work for the
Vite dev server and the Tauri origin — and only for those (architecture §5)."""

ALLOWED_ORIGIN = "http://localhost:1420"


def test_the_dev_server_origin_is_allowed(client):
    response = client.post(
        "/api/auth/login",
        json={"password": "wrong"},
        headers={"Origin": ALLOWED_ORIGIN},
    )
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN


def test_preflight_allows_the_authorization_header(client):
    response = client.options(
        "/api/positions",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


def test_an_unknown_origin_is_not_granted_access(client):
    response = client.post(
        "/api/auth/login",
        json={"password": "wrong"},
        headers={"Origin": "https://evil.example.com"},
    )
    assert "access-control-allow-origin" not in response.headers
