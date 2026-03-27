from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
for path in (
    REPO_ROOT / ".codex_deps",
    REPO_ROOT / "packages" / "shared-config" / "src",
    REPO_ROOT / "packages" / "shared-schemas" / "src",
):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from alembic import command
from alembic.config import Config


def build_config(database_url: str | None = None) -> Config:
    config = Config(str(REPO_ROOT / "infra" / "alembic.ini"))
    if database_url is not None:
        config.set_main_option("sqlalchemy.url", database_url)
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DungeonCore Alembic migrations.")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--revision", default="head")
    args = parser.parse_args()

    command.upgrade(build_config(args.database_url), args.revision)


if __name__ == "__main__":
    main()
