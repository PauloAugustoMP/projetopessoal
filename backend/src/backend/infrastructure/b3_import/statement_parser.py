"""Parser for the B3 investor-portal "extrato de movimentação" (CSV or Excel).

Expected columns (as exported by the portal):
    Entrada/Saída; Data; Movimentação; Produto; Instituição; Quantidade;
    Preço unitário; Valor da Operação

Each row is classified as a trade (buy/sell), a dividend, or a corporate action
(docs/business-rules.md §7). Known-irrelevant movement types are skipped
silently; anything unrecognized or missing required data lands in the
manual-review list instead of failing the whole import.

Corporate-action quantity semantics (how the portal reports them):
- Desdobro (split) / Bonificação: a CREDIT with the ADDITIONAL shares received.
- Grupamento (reverse split): a DEBIT with the shares removed, or a CREDIT with
  the new total — both are accepted; the factor is derived later against the
  position on that date.
"""

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal, Optional


@dataclass(frozen=True)
class ParsedTrade:
    row: int
    ticker: str
    type: Literal["buy", "sell"]
    quantity: float
    price_per_share: float
    date: str  # ISO


@dataclass(frozen=True)
class ParsedDividend:
    row: int
    ticker: str
    type: Literal["dividend", "jcp", "reit_income"]
    quantity: float
    gross_value_per_share: float
    payment_date: str  # ISO


@dataclass(frozen=True)
class ParsedCorporateActionEvent:
    row: int
    ticker: str
    type: Literal["split", "reverse_split", "bonus_shares"]
    date: str  # ISO
    direction: Literal["credit", "debit"]
    quantity: float


@dataclass(frozen=True)
class ReviewRow:
    row: int
    reason: str
    raw: str


@dataclass
class ParsedStatement:
    trades: list[ParsedTrade] = field(default_factory=list)
    dividends: list[ParsedDividend] = field(default_factory=list)
    corporate_actions: list[ParsedCorporateActionEvent] = field(default_factory=list)
    review_rows: list[ReviewRow] = field(default_factory=list)


class StatementFormatError(Exception):
    pass


def _normalize(text: str) -> str:
    stripped = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(stripped.lower().split())


EXPECTED_COLUMNS = {
    "entrada/saida": "direction",
    "data": "date",
    "movimentacao": "movement",
    "produto": "product",
    "instituicao": "institution",
    "quantidade": "quantity",
    "preco unitario": "unit_price",
    "valor da operacao": "total_value",
}

TRADE_MOVEMENTS = {"transferencia - liquidacao"}
SUBSCRIPTION_BUY_MOVEMENTS = {
    "direitos de subscricao - exercido",
    "direito de subscricao - exercido",
    "subscricao exercida",
}
DIVIDEND_MOVEMENTS: dict[str, Literal["dividend", "jcp", "reit_income"]] = {
    "dividendo": "dividend",
    "juros sobre capital proprio": "jcp",
    "rendimento": "reit_income",
}
CORPORATE_ACTION_MOVEMENTS: dict[str, Literal["split", "reverse_split", "bonus_shares"]] = {
    "desdobro": "split",
    "desdobramento": "split",
    "grupamento": "reverse_split",
    "bonificacao em ativos": "bonus_shares",
}
IGNORED_MOVEMENTS = {
    "atualizacao",
    "emprestimo",
    "emprestimo de ativos",
    "transferencia",
    "direitos de subscricao - nao exercido",
    "direito de subscricao - nao exercido",
    "cessao de direitos",
    "cessao de direitos - solicitada",
    "leilao de fracao",
    "fracao em ativos",
}


def _parse_number(value: object) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text in ("", "-"):
        return None
    text = text.replace("R$", "").strip()
    # Brazilian format: 1.234,56 — and 1.000 (dot as thousands separator, no decimals)
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", text):
        text = text.replace(".", "")
    try:
        return float(text)
    except ValueError:
        return None


def _parse_date(value: object) -> Optional[str]:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _extract_ticker(product: object) -> Optional[str]:
    text = str(product or "").strip()
    if not text:
        return None
    ticker = text.split(" - ")[0].strip().upper()
    return ticker or None


def _read_raw_rows(content: bytes, filename: str) -> list[list[object]]:
    if filename.lower().endswith((".xlsx", ".xls")):
        try:
            from openpyxl import load_workbook

            workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception as error:
            raise StatementFormatError(f"Could not read the Excel file: {error}") from error
        sheet = workbook.active
        return [list(row) for row in sheet.iter_rows(values_only=True)]

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    sample = text[:2048]
    delimiter = ";" if sample.count(";") >= sample.count(",") else ","
    return [list(row) for row in csv.reader(io.StringIO(text), delimiter=delimiter)]


def parse_statement(content: bytes, filename: str) -> ParsedStatement:
    raw_rows = _read_raw_rows(content, filename)
    if not raw_rows:
        raise StatementFormatError("The file is empty.")

    header = [_normalize(str(cell or "")) for cell in raw_rows[0]]
    columns = {EXPECTED_COLUMNS[name]: index for index, name in enumerate(header) if name in EXPECTED_COLUMNS}
    missing = set(EXPECTED_COLUMNS.values()) - {"institution", "total_value"} - set(columns)
    if missing:
        raise StatementFormatError(
            "The file does not look like a B3 movement statement — missing columns: "
            + ", ".join(sorted(missing))
        )

    result = ParsedStatement()

    for row_number, cells in enumerate(raw_rows[1:], start=2):
        if not any(str(cell or "").strip() for cell in cells):
            continue
        raw = "; ".join(str(cell or "") for cell in cells)

        def cell(name: str) -> object:
            index = columns.get(name)
            return cells[index] if index is not None and index < len(cells) else None

        movement = _normalize(str(cell("movement") or ""))
        direction_text = _normalize(str(cell("direction") or ""))
        direction = "credit" if direction_text.startswith("cred") else "debit"
        ticker = _extract_ticker(cell("product"))
        parsed_date = _parse_date(cell("date"))
        quantity = _parse_number(cell("quantity"))
        unit_price = _parse_number(cell("unit_price"))

        def review(reason: str) -> None:
            result.review_rows.append(ReviewRow(row=row_number, reason=reason, raw=raw))

        if movement in IGNORED_MOVEMENTS:
            continue
        if ticker is None or parsed_date is None:
            review("Missing or unreadable ticker/date.")
            continue

        if movement in TRADE_MOVEMENTS or movement in SUBSCRIPTION_BUY_MOVEMENTS:
            if quantity is None or quantity <= 0 or unit_price is None:
                review("Trade row without a readable quantity/unit price.")
                continue
            trade_type: Literal["buy", "sell"] = (
                "buy" if (movement in SUBSCRIPTION_BUY_MOVEMENTS or direction == "credit") else "sell"
            )
            result.trades.append(
                ParsedTrade(
                    row=row_number,
                    ticker=ticker,
                    type=trade_type,
                    quantity=quantity,
                    price_per_share=unit_price,
                    date=parsed_date,
                )
            )
        elif movement in DIVIDEND_MOVEMENTS:
            if quantity is None or quantity <= 0 or unit_price is None:
                review("Dividend row without a readable quantity/unit value.")
                continue
            result.dividends.append(
                ParsedDividend(
                    row=row_number,
                    ticker=ticker,
                    type=DIVIDEND_MOVEMENTS[movement],
                    quantity=quantity,
                    gross_value_per_share=unit_price,
                    payment_date=parsed_date,
                )
            )
        elif movement in CORPORATE_ACTION_MOVEMENTS:
            if quantity is None or quantity <= 0:
                review("Corporate action row without a readable quantity.")
                continue
            result.corporate_actions.append(
                ParsedCorporateActionEvent(
                    row=row_number,
                    ticker=ticker,
                    type=CORPORATE_ACTION_MOVEMENTS[movement],
                    date=parsed_date,
                    direction=direction,  # type: ignore[arg-type]
                    quantity=quantity,
                )
            )
        else:
            review(f'Unrecognized movement type: "{cell("movement")}".')

    return result
