from tests.factories import transaction_payload


def _positions(client, auth_headers) -> dict[str, dict]:
    response = client.get("/api/positions", headers=auth_headers)
    assert response.status_code == 200
    return {p["ticker"]: p for p in response.json()}


def test_creating_a_buy_persists_it_and_recalculates_the_position(client, auth_headers):
    response = client.post(
        "/api/transactions",
        json=transaction_payload(quantity=100, pricePerShare=10, fees=2),
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["ticker"] == "ITSA4"
    assert body["pricePerShare"] == 10
    assert body["source"] == "manual"
    assert body["recalculating"] is True

    # TestClient runs the background task before returning, so the position is ready.
    positions = _positions(client, auth_headers)
    assert positions["ITSA4"]["quantity"] == 100
    assert positions["ITSA4"]["averagePrice"] == (100 * 10 + 2) / 100
    assert positions["ITSA4"]["category"] == "stock"


def test_a_backdated_buy_recalculates_the_average_price_chronologically(client, auth_headers):
    client.post("/api/transactions", json=transaction_payload(quantity=100, pricePerShare=10, date="2026-01-10"), headers=auth_headers)
    client.post("/api/transactions", json=transaction_payload(quantity=100, pricePerShare=20, date="2026-02-10"), headers=auth_headers)
    assert _positions(client, auth_headers)["ITSA4"]["averagePrice"] == 15

    # Backdated entry BEFORE the two existing ones.
    response = client.post(
        "/api/transactions",
        json=transaction_payload(quantity=200, pricePerShare=5, date="2026-01-05"),
        headers=auth_headers,
    )
    assert response.status_code == 201

    position = _positions(client, auth_headers)["ITSA4"]
    assert position["quantity"] == 400
    assert position["averagePrice"] == (200 * 5 + 100 * 10 + 100 * 20) / 400


def test_selling_the_entire_position_removes_it_from_the_listing(client, auth_headers):
    client.post("/api/transactions", json=transaction_payload(quantity=100, pricePerShare=10, date="2026-01-10"), headers=auth_headers)
    client.post(
        "/api/transactions",
        json=transaction_payload(type="sell", quantity=100, pricePerShare=12, date="2026-01-20"),
        headers=auth_headers,
    )
    assert "ITSA4" not in _positions(client, auth_headers)


def test_selling_more_than_the_position_on_that_date_is_blocked(client, auth_headers):
    client.post("/api/transactions", json=transaction_payload(quantity=100, pricePerShare=10, date="2026-01-10"), headers=auth_headers)
    response = client.post(
        "/api/transactions",
        json=transaction_payload(type="sell", quantity=150, pricePerShare=12, date="2026-01-20"),
        headers=auth_headers,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "SELL_EXCEEDS_POSITION"
    # Nothing was saved.
    listing = client.get("/api/transactions", headers=auth_headers).json()
    assert len(listing) == 1


def test_a_sell_backdated_to_before_the_buy_is_blocked(client, auth_headers):
    client.post("/api/transactions", json=transaction_payload(quantity=100, pricePerShare=10, date="2026-01-10"), headers=auth_headers)
    response = client.post(
        "/api/transactions",
        json=transaction_payload(type="sell", quantity=50, pricePerShare=12, date="2026-01-05"),
        headers=auth_headers,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "SELL_EXCEEDS_POSITION"


def test_an_unknown_ticker_is_blocked(client, auth_headers):
    response = client.post(
        "/api/transactions", json=transaction_payload(ticker="XXXX9"), headers=auth_headers
    )
    assert response.status_code == 400
    assert response.json()["code"] == "UNKNOWN_TICKER"


def test_an_invalid_payload_returns_400_in_the_error_shape(client, auth_headers):
    response = client.post(
        "/api/transactions", json=transaction_payload(quantity=-5), headers=auth_headers
    )
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert "quantity" in body["message"]


def test_listing_filters_by_ticker_and_date_range(client, auth_headers):
    client.post("/api/transactions", json=transaction_payload(ticker="ITSA4", date="2026-01-10"), headers=auth_headers)
    client.post("/api/transactions", json=transaction_payload(ticker="PETR4", date="2026-02-10"), headers=auth_headers)

    by_ticker = client.get("/api/transactions", params={"ticker": "petr4"}, headers=auth_headers).json()
    assert [t["ticker"] for t in by_ticker] == ["PETR4"]

    by_range = client.get(
        "/api/transactions", params={"from": "2026-02-01", "to": "2026-02-28"}, headers=auth_headers
    ).json()
    assert [t["ticker"] for t in by_range] == ["PETR4"]


def test_getting_a_transaction_by_id_and_404_for_a_missing_one(client, auth_headers):
    created = client.post("/api/transactions", json=transaction_payload(), headers=auth_headers).json()
    fetched = client.get(f"/api/transactions/{created['id']}", headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json()["id"] == created["id"]

    missing = client.get(
        "/api/transactions/00000000-0000-0000-0000-000000000000", headers=auth_headers
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == "TRANSACTION_NOT_FOUND"


def test_editing_a_transaction_triggers_recalculation(client, auth_headers):
    created = client.post(
        "/api/transactions",
        json=transaction_payload(quantity=100, pricePerShare=10),
        headers=auth_headers,
    ).json()

    response = client.patch(
        f"/api/transactions/{created['id']}",
        json=transaction_payload(quantity=50, pricePerShare=8),
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["recalculating"] is True

    position = _positions(client, auth_headers)["ITSA4"]
    assert position["quantity"] == 50
    assert position["averagePrice"] == 8


def test_editing_a_buy_cannot_invalidate_a_later_sell(client, auth_headers):
    buy = client.post(
        "/api/transactions",
        json=transaction_payload(quantity=100, pricePerShare=10, date="2026-01-10"),
        headers=auth_headers,
    ).json()
    client.post(
        "/api/transactions",
        json=transaction_payload(type="sell", quantity=80, pricePerShare=12, date="2026-01-20"),
        headers=auth_headers,
    )

    response = client.patch(
        f"/api/transactions/{buy['id']}",
        json=transaction_payload(quantity=50, pricePerShare=10, date="2026-01-10"),
        headers=auth_headers,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "SELL_EXCEEDS_POSITION"


def test_deleting_a_transaction_recalculates_the_position(client, auth_headers):
    client.post("/api/transactions", json=transaction_payload(quantity=100, pricePerShare=10, date="2026-01-10"), headers=auth_headers)
    second = client.post(
        "/api/transactions",
        json=transaction_payload(quantity=100, pricePerShare=20, date="2026-02-10"),
        headers=auth_headers,
    ).json()

    response = client.delete(f"/api/transactions/{second['id']}", headers=auth_headers)
    assert response.status_code == 204

    position = _positions(client, auth_headers)["ITSA4"]
    assert position["quantity"] == 100
    assert position["averagePrice"] == 10


def test_deleting_a_buy_that_backs_a_later_sell_is_blocked(client, auth_headers):
    buy = client.post(
        "/api/transactions",
        json=transaction_payload(quantity=100, pricePerShare=10, date="2026-01-10"),
        headers=auth_headers,
    ).json()
    client.post(
        "/api/transactions",
        json=transaction_payload(type="sell", quantity=80, pricePerShare=12, date="2026-01-20"),
        headers=auth_headers,
    )

    response = client.delete(f"/api/transactions/{buy['id']}", headers=auth_headers)
    assert response.status_code == 422
    assert response.json()["code"] == "SELL_EXCEEDS_POSITION"
