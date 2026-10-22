import io
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from app.models import Base


def migration_config():
    return Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))


def test_migration_roundtrip_matches_models(tmp_path, monkeypatch, settings):
    database_url = f"sqlite:///{tmp_path / 'migration.db'}"
    monkeypatch.setattr(settings, "database_url", database_url)
    config = migration_config()
    command.upgrade(config, "head")
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
        command.downgrade(config, "base")
        assert inspect(engine).get_table_names() == ["alembic_version"]
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
    finally:
        engine.dispose()


def test_migration_generates_postgresql_sql_without_connection(monkeypatch, settings):
    monkeypatch.setattr(settings, "database_url", "postgresql+psycopg://unused:unused@localhost/unused")
    config = migration_config()
    config.output_buffer = io.StringIO()
    command.upgrade(config, "head", sql=True)
    sql = config.output_buffer.getvalue()
    assert "CREATE TABLE events" in sql
    assert "CREATE TABLE rule_states" in sql
    assert "CREATE INDEX ix_logs_service_level_time" in sql
