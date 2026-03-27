from __future__ import annotations

import logging
from contextlib import suppress
from pathlib import Path

import pika
import redis
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .settings import AppSettings

logger = logging.getLogger(__name__)


def create_postgres_engine(settings: AppSettings, *, echo: bool = False) -> Engine:
    return create_engine(settings.postgres_dsn, future=True, echo=echo)


def run_alembic_migrations(engine: Engine, alembic_ini_path: str | Path | None = None) -> None:
    """Run Alembic migrations programmatically using the provided engine.
    
    Args:
        engine: SQLAlchemy engine to run migrations against
        alembic_ini_path: Path to alembic.ini file. If None, tries common locations.
    """
    from alembic import command
    from alembic.config import Config

    if alembic_ini_path is None:
        possible_paths = [
            Path("/workspace/infra/alembic.ini"),  # Docker container path
            Path("/app/infra/alembic.ini"),
            Path("infra/alembic.ini"),  # Local dev from repo root
            Path("alembic.ini"),
            Path(__file__).resolve().parents[4] / "infra" / "alembic.ini",
        ]
        for p in possible_paths:
            if p.exists():
                alembic_ini_path = p
                logger.info("Found alembic.ini at: %s", p)
                break
    
    if alembic_ini_path is None or not Path(alembic_ini_path).exists():
        logger.warning("Alembic config not found, skipping migrations. Searched paths: %s", 
                      [str(p) for p in possible_paths] if 'possible_paths' in dir() else "N/A")
        return

    alembic_ini = Path(alembic_ini_path).resolve()
    alembic_cfg = Config(str(alembic_ini))
    
    # Ensure script_location is absolute so it works regardless of cwd
    script_location = alembic_ini.parent / "alembic"
    if script_location.exists():
        alembic_cfg.set_main_option("script_location", str(script_location))
        logger.info("Set alembic script_location to: %s", script_location)
    
    with engine.begin() as connection:
        alembic_cfg.attributes["connection"] = connection
        alembic_cfg.set_main_option("sqlalchemy.url", str(engine.url))
        
        logger.info("Running Alembic migrations...")
        command.upgrade(alembic_cfg, "head")
        logger.info("Alembic migrations completed")


def create_redis_client(settings: AppSettings) -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def create_rabbitmq_connection_parameters(settings: AppSettings) -> pika.URLParameters:
    return pika.URLParameters(settings.rabbitmq_url)


def check_postgres_health(settings: AppSettings) -> bool:
    with suppress(Exception):
        engine = create_postgres_engine(settings)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    return False


def check_redis_health(settings: AppSettings) -> bool:
    with suppress(Exception):
        client = create_redis_client(settings)
        return bool(client.ping())
    return False


def check_rabbitmq_health(settings: AppSettings) -> bool:
    with suppress(Exception):
        parameters = create_rabbitmq_connection_parameters(settings)
        connection = pika.BlockingConnection(parameters)
        connection.close()
        return True
    return False
