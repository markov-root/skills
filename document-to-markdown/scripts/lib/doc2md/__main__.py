"""Enable ``python -m doc2md`` as the CLI entry point."""

from doc2md.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
