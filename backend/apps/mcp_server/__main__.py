"""Module entrypoint so ``python -m apps.mcp_server`` works."""

from .server import main


if __name__ == "__main__":
    raise SystemExit(main())
