from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _upload(client, auth_headers, filename: str):
    content = (FIXTURES / filename).read_bytes()
    return client.post(
        "/api/import/b3-statement",
        files={"file": (filename, content, "text/csv")},
        headers=auth_headers,
    )


def test_importing_a_statement_creates_everything_and_recalculates_positions(client, auth_headers):
    response = _upload(client, auth_headers, "b3_movimentacao_sample.csv")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["transactionsCreated"] == 3
    assert body["dividendsCreated"] == 3
    assert body["corporateActionsCreated"] == 3
    assert body["duplicatesSkipped"] == 0
    assert len(body["rowsForManualReview"]) == 1  # the unknown movement type

    positions = {p["ticker"]: p for p in client.get("/api/positions", headers=auth_headers).json()}
    # ITSA4: buy 100@9.10, sell 40 -> 60@9.10; split x2 -> 120@4.55; 10% bonus -> 132
    assert positions["ITSA4"]["quantity"] == 132
    assert positions["ITSA4"]["averagePrice"] == pytest.approx(60 * 9.10 / 132)
    # MXRF11: buy 50@10; 10:1 reverse split -> 5@100
    assert positions["MXRF11"]["quantity"] == 5
    assert positions["MXRF11"]["averagePrice"] == pytest.approx(100)

    actions = client.get("/api/corporate-actions", params={"ticker": "ITSA4"}, headers=auth_headers).json()
    assert [(a["type"], a["factor"]) for a in actions] == [("split", 2.0), ("bonus_shares", 0.1)]

    imported = client.get("/api/transactions", params={"ticker": "ITSA4"}, headers=auth_headers).json()
    assert all(t["source"] == "b3_import" for t in imported)


def test_importing_the_same_statement_twice_does_not_duplicate_anything(client, auth_headers):
    first = _upload(client, auth_headers, "b3_movimentacao_sample.csv").json()
    second = _upload(client, auth_headers, "b3_movimentacao_sample.csv").json()

    assert second["transactionsCreated"] == 0
    assert second["dividendsCreated"] == 0
    assert second["corporateActionsCreated"] == 0
    assert second["duplicatesSkipped"] == (
        first["transactionsCreated"] + first["dividendsCreated"] + first["corporateActionsCreated"]
    )

    transactions = client.get("/api/transactions", headers=auth_headers).json()
    assert len(transactions) == 3

    positions = {p["ticker"]: p for p in client.get("/api/positions", headers=auth_headers).json()}
    assert positions["ITSA4"]["quantity"] == 132  # unchanged


def test_a_transaction_entered_manually_is_recognized_as_a_duplicate(client, auth_headers):
    created = client.post(
        "/api/transactions",
        json={"ticker": "ITSA4", "type": "buy", "quantity": 100, "pricePerShare": 9.10, "date": "2026-01-10"},
        headers=auth_headers,
    )
    assert created.status_code == 201

    body = _upload(client, auth_headers, "b3_movimentacao_sample.csv").json()
    assert body["transactionsCreated"] == 2  # the ITSA4 buy was skipped
    assert body["duplicatesSkipped"] == 1


def test_a_sell_larger_than_the_position_is_flagged_for_review_not_rejected(client, auth_headers):
    response = _upload(client, auth_headers, "b3_movimentacao_sell_exceeds.csv")
    assert response.status_code == 200
    body = response.json()

    # Both rows are saved (batch import), but the inconsistency is flagged (§10).
    assert body["transactionsCreated"] == 2
    assert any("Inconsistent history" in r["reason"] for r in body["rowsForManualReview"])


def test_a_file_that_is_not_a_statement_returns_400(client, auth_headers):
    response = client.post(
        "/api/import/b3-statement",
        files={"file": ("random.csv", b"id,name\n1,foo\n", "text/csv")},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_STATEMENT_FILE"


def test_unknown_tickers_are_registered_from_the_statement_itself(client, auth_headers):
    """A statement is authoritative and carries the product name, so an unknown
    ticker is registered rather than rejected — the typo guard (§10) belongs to
    hand-typed entries, not to imports."""
    csv_content = (
        "Entrada/Saída;Data;Movimentação;Produto;Instituição;Quantidade;Preço unitário;Valor da Operação\n"
        "Credito;10/01/2026;Transferência - Liquidação;TRXF11 - TRX REAL ESTATE FDO INV IMOB;COR;10;R$ 100,00;R$ 1.000,00\n"
        "Credito;20/01/2026;Rendimento;TRXF11 - TRX REAL ESTATE FDO INV IMOB;COR;10;R$ 0,90;R$ 9,00\n"
        "Credito;10/02/2026;Transferência - Liquidação;ALOS3 - ALLOS S.A.;COR;50;R$ 20,00;R$ 1.000,00\n"
        "Credito;20/02/2026;Dividendo;ALOS3 - ALLOS S.A.;COR;50;R$ 0,30;R$ 15,00\n"
    ).encode("utf-8")

    response = client.post(
        "/api/import/b3-statement",
        files={"file": ("extrato.csv", csv_content, "text/csv")},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["assetsCreated"] == 2
    assert body["transactionsCreated"] == 2
    assert body["rowsForManualReview"] == []

    assets = {a["ticker"]: a for a in client.get("/api/assets", headers=auth_headers).json()}
    # Category inferred from the payout each one made, not from a guess.
    assert assets["TRXF11"]["category"] == "reit"
    assert assets["ALOS3"]["category"] == "stock"
    assert assets["TRXF11"]["name"] == "TRX REAL ESTATE FDO INV IMOB"

    positions = {p["ticker"]: p for p in client.get("/api/positions", headers=auth_headers).json()}
    assert positions["TRXF11"]["quantity"] == 10
    assert positions["ALOS3"]["quantity"] == 50


def test_reimporting_does_not_recreate_assets(client, auth_headers):
    csv_content = (
        "Entrada/Saída;Data;Movimentação;Produto;Instituição;Quantidade;Preço unitário;Valor da Operação\n"
        "Credito;10/01/2026;Compra;KNCR11 - KINEA RENDIMENTOS IMOB;COR;10;R$ 100,00;R$ 1.000,00\n"
    ).encode("utf-8")
    files = {"file": ("extrato.csv", csv_content, "text/csv")}

    first = client.post("/api/import/b3-statement", files=files, headers=auth_headers).json()
    second = client.post(
        "/api/import/b3-statement",
        files={"file": ("extrato.csv", csv_content, "text/csv")},
        headers=auth_headers,
    ).json()

    assert first["assetsCreated"] == 1
    assert second["assetsCreated"] == 0
    assert second["duplicatesSkipped"] == 1
