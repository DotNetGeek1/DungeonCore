# shared-schemas

Canonical Pydantic v2 contracts for DungeonCore services, agents, and UI clients.

Included in this package:
- canonical state models such as `GameState`, `CharacterState`, and `NpcState`
- typed action and `PlayerTurn` contracts
- typed `GameEvent` envelopes with trace and correlation IDs
- communication, memory, agent context, and API DTOs
- canonical example payloads
- JSON Schema export utility

Local workflow:

```bash
python -m pytest packages/shared-schemas/tests
python -m mypy packages/shared-schemas/src/shared_schemas
python packages/shared-schemas/scripts/export_schemas.py
```
