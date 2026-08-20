from tests.integration.conftest import TEST_PASSWORD


def test_login_with_the_correct_password_returns_both_tokens(client):
    response = client.post("/api/auth/login", json={"password": TEST_PASSWORD})
    assert response.status_code == 200
    body = response.json()
    assert body["accessToken"]
    assert body["refreshToken"]
    assert body["accessToken"] != body["refreshToken"]


def test_login_with_a_wrong_password_is_rejected(client):
    response = client.post("/api/auth/login", json={"password": "wrong"})
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_refresh_token_yields_a_new_access_token(client):
    login = client.post("/api/auth/login", json={"password": TEST_PASSWORD}).json()
    response = client.post("/api/auth/refresh", json={"refreshToken": login["refreshToken"]})
    assert response.status_code == 200
    assert response.json()["accessToken"]


def test_an_access_token_cannot_be_used_as_a_refresh_token(client):
    login = client.post("/api/auth/login", json={"password": TEST_PASSWORD}).json()
    response = client.post("/api/auth/refresh", json={"refreshToken": login["accessToken"]})
    assert response.status_code == 401


def test_protected_routes_reject_requests_without_a_token(client):
    for path in ["/api/transactions", "/api/positions", "/api/assets"]:
        assert client.get(path).status_code == 401, path


def test_protected_routes_reject_a_garbage_token(client):
    response = client.get("/api/positions", headers={"Authorization": "Bearer nonsense"})
    assert response.status_code == 401
