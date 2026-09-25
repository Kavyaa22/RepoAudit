"""Allow running as `python -m repoaudit`."""

from repoaudit.interfaces.cli.cli import cli

if __name__ == "__main__":
    cli()
