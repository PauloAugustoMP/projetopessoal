def test_autocomplete_matches_ticker_and_name_case_insensitively(client, auth_headers):
    response = client.get("/api/assets", params={"q": "ita"}, headers=auth_headers)
    assert response.status_code == 200
    tickers = [a["ticker"] for a in response.json()]
    assert "ITSA4" in tickers  # matches the name "Itaúsa"
    assert "ITUB4" in tickers
    assert "PETR4" not in tickers


def test_listing_without_a_query_returns_the_catalog(client, auth_headers):
    response = client.get("/api/assets", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()) >= 15


def test_asset_detail_and_404_for_an_unknown_ticker(client, auth_headers):
    found = client.get("/api/assets/itsa4", headers=auth_headers)
    assert found.status_code == 200
    assert found.json() == {
        "ticker": "ITSA4",
        "name": "Itaúsa PN",
        "category": "stock",
        "logoUrl": None,
    }

    missing = client.get("/api/assets/XXXX9", headers=auth_headers)
    assert missing.status_code == 404
    assert missing.json()["code"] == "ASSET_NOT_FOUND"
