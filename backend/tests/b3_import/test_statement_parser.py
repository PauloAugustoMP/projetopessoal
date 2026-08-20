import io
from pathlib import Path

import pytest

from backend.infrastructure.b3_import.statement_parser import (
    StatementFormatError,
    parse_statement,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SAMPLE_CSV = (FIXTURES / "b3_movimentacao_sample.csv").read_bytes()


def _sample_as_xlsx() -> bytes:
    """Same statement content, but as the portal's Excel export."""
    from openpyxl import Workbook

    text = SAMPLE_CSV.decode("utf-8")
    workbook = Workbook()
    sheet = workbook.active
    for line in text.strip().splitlines():
        sheet.append(line.split(";"))
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_parses_buys_and_sells_from_liquidation_rows():
    statement = parse_statement(SAMPLE_CSV, "extrato.csv")
    trades = {(t.ticker, t.type): t for t in statement.trades}
    assert len(statement.trades) == 3

    buy = trades[("ITSA4", "buy")]
    assert buy.quantity == 100
    assert buy.price_per_share == 9.10
    assert buy.date == "2026-01-10"

    sell = trades[("ITSA4", "sell")]
    assert sell.quantity == 40
    assert sell.price_per_share == 10.0

    assert trades[("MXRF11", "buy")].date == "2026-02-10"


def test_parses_dividends_with_type_classification():
    statement = parse_statement(SAMPLE_CSV, "extrato.csv")
    by_type = {(d.ticker, d.type): d for d in statement.dividends}
    assert len(statement.dividends) == 3

    assert by_type[("ITSA4", "dividend")].gross_value_per_share == 0.25
    assert by_type[("ITSA4", "jcp")].gross_value_per_share == 0.10
    assert by_type[("MXRF11", "reit_income")].payment_date == "2026-02-15"


def test_parses_split_bonus_and_reverse_split_events():
    statement = parse_statement(SAMPLE_CSV, "extrato.csv")
    by_type = {(a.ticker, a.type): a for a in statement.corporate_actions}
    assert len(statement.corporate_actions) == 3

    split = by_type[("ITSA4", "split")]
    assert split.quantity == 60
    assert split.direction == "credit"
    assert split.date == "2026-03-01"

    bonus = by_type[("ITSA4", "bonus_shares")]
    assert bonus.quantity == 12

    reverse = by_type[("MXRF11", "reverse_split")]
    assert reverse.quantity == 45
    assert reverse.direction == "debit"


def test_unknown_movements_go_to_review_and_irrelevant_ones_are_skipped():
    statement = parse_statement(SAMPLE_CSV, "extrato.csv")
    # "Atualização" is silently ignored; "Movimento Desconhecido" needs review.
    assert len(statement.review_rows) == 1
    assert "Movimento Desconhecido" in statement.review_rows[0].reason
    assert statement.review_rows[0].row == 12


def test_excel_file_parses_identically_to_csv():
    from_csv = parse_statement(SAMPLE_CSV, "extrato.csv")
    from_xlsx = parse_statement(_sample_as_xlsx(), "extrato.xlsx")
    assert [(t.ticker, t.type, t.quantity, t.price_per_share, t.date) for t in from_xlsx.trades] == [
        (t.ticker, t.type, t.quantity, t.price_per_share, t.date) for t in from_csv.trades
    ]
    assert len(from_xlsx.dividends) == len(from_csv.dividends)
    assert len(from_xlsx.corporate_actions) == len(from_csv.corporate_actions)


def test_brazilian_number_formats_are_parsed():
    csv_content = (
        "Entrada/Saída;Data;Movimentação;Produto;Instituição;Quantidade;Preço unitário;Valor da Operação\n"
        "Credito;10/01/2026;Transferência - Liquidação;VALE3 - VALE ON;X;1.000;R$ 1.234,56;R$ 1.234.560,00\n"
    ).encode("utf-8")
    statement = parse_statement(csv_content, "extrato.csv")
    assert statement.trades[0].quantity == 1000
    assert statement.trades[0].price_per_share == 1234.56


def test_a_file_that_is_not_a_statement_is_rejected():
    with pytest.raises(StatementFormatError):
        parse_statement(b"id,name\n1,foo\n", "random.csv")


def test_a_trade_row_without_a_price_goes_to_review():
    csv_content = (
        "Entrada/Saída;Data;Movimentação;Produto;Instituição;Quantidade;Preço unitário;Valor da Operação\n"
        "Credito;10/01/2026;Transferência - Liquidação;VALE3 - VALE ON;X;100;-;-\n"
    ).encode("utf-8")
    statement = parse_statement(csv_content, "extrato.csv")
    assert statement.trades == []
    assert len(statement.review_rows) == 1
