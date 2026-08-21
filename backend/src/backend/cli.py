"""Small maintenance commands:

    uv run python -m backend.cli hash-password
    uv run python -m backend.cli inspect-statement <file>
"""

import getpass
import sys

from backend.api.security import hash_password


def _hash_password() -> None:
    password = getpass.getpass("Password: ")
    confirmation = getpass.getpass("Confirm: ")
    if password != confirmation:
        print("Passwords do not match.", file=sys.stderr)
        raise SystemExit(1)
    print("\nSet this in your .env as APP_PASSWORD_HASH (between single quotes):")
    print(hash_password(password))


def _inspect_statement(path: str) -> None:
    """Prints only the STRUCTURE of a B3 export — header labels and column counts,
    never the row values — so an unrecognized layout can be diagnosed without
    sharing any financial data."""
    from backend.infrastructure.b3_import.statement_parser import (
        EXPECTED_COLUMNS,
        _normalize,
        _read_raw_rows,
    )

    with open(path, "rb") as handle:
        content = handle.read()

    rows = _read_raw_rows(content, path)
    print(f"File: {path}")
    print(f"Rows read: {len(rows)}")
    if not rows:
        print("The file produced no rows — wrong format or an empty export.")
        return

    for index, row in enumerate(rows[:6]):
        labels = [str(cell or "").strip() for cell in row]
        filled = sum(1 for label in labels if label)
        matches = sum(1 for label in labels if _normalize(label) in EXPECTED_COLUMNS)
        print(f"\n--- row {index + 1}: {len(labels)} cells, {filled} non-empty, {matches} recognized ---")
        for position, label in enumerate(labels):
            normalized = _normalize(label)
            if normalized in EXPECTED_COLUMNS:
                print(f"  [{position}] MATCH {label!r}")
            elif index == 0:
                # Row 1 is the header candidate: showing its labels is what
                # diagnoses the mismatch, and headers carry no financial data.
                print(f"  [{position}]       {label!r}  (normalized: {normalized!r})")
            else:
                # Never print values from data rows — this output gets shared.
                print(f"  [{position}]       <value omitted>")

    print("\nColumn labels the parser expects:")
    for name in EXPECTED_COLUMNS:
        print(f"  - {name!r}")


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "hash-password":
        _hash_password()
    elif command == "inspect-statement":
        if len(sys.argv) < 3:
            print("Usage: python -m backend.cli inspect-statement <file>", file=sys.stderr)
            raise SystemExit(2)
        _inspect_statement(sys.argv[2])
    else:
        print(
            "Usage:\n"
            "  python -m backend.cli hash-password\n"
            "  python -m backend.cli inspect-statement <file>",
            file=sys.stderr,
        )
        raise SystemExit(2)


if __name__ == "__main__":
    main()
