"""Small maintenance commands: `uv run python -m backend.cli hash-password`."""

import getpass
import sys

from backend.api.security import hash_password


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command != "hash-password":
        print("Usage: python -m backend.cli hash-password", file=sys.stderr)
        raise SystemExit(2)
    password = getpass.getpass("Password: ")
    confirmation = getpass.getpass("Confirm: ")
    if password != confirmation:
        print("Passwords do not match.", file=sys.stderr)
        raise SystemExit(1)
    print("\nSet this in your .env as APP_PASSWORD_HASH:")
    print(hash_password(password))


if __name__ == "__main__":
    main()
