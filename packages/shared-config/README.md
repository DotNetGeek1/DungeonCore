# shared-config

Shared environment parsing, persistence, cache, and queue primitives for DungeonCore.

Included in this package:
- canonical app/service settings loaded from environment variables
- Postgres engine/repository helpers and Alembic migration runner support
- Redis coordination primitives
- RabbitMQ topology definitions and publish/consume helpers
- lightweight placeholder-service health wiring for the current service skeleton

Local workflow:

```bash
$env:PYTHONPATH = ".codex_deps"
python -m pytest packages/shared-config/tests
python packages/shared-config/scripts/run_migrations.py --help
```
