# 🐉 DungeonCore
### *A Multi-Agent D&D Engine*

> *In a realm where code and chaos intertwine… a party of artificial minds ventures forth.*
>
> *A Dungeon Master that never tires.*
> *A party that never logs off.*
> *A world that evolves with every turn.*

---

## 🎲 What is DungeonCore?

**DungeonCore** is a system where autonomous agents play Dungeons & Dragons together inside a structured, observable engine.

- 🧙 One agent becomes the **Dungeon Master**
- 🛡 Multiple agents take the role of **player characters**
- ⚙️ A deterministic **rules engine** governs reality
- 💬 A structured **communication system** enables coordination
- 🧑‍💻 Humans may **observe, intervene, or take control at will**

This is not a chatbot.

This is a **living campaign engine**.

---

## 🧠 Why this exists

Most “multi-agent” systems are just:
- glorified chatrooms  
- agents politely hallucinating at each other  

DungeonCore introduces something far more dangerous:

> **constraints**

Agents must operate under:
- strict turn order  
- incomplete information  
- hard rules  
- limited communication  
- persistent consequences  

If agents can survive here…

they can survive anywhere.

---

## 🏰 The Architecture of the Realm

```text
Frontend (React)
        ↓
API / Orchestrator
        ↓
Agent Runtime (Python)
        ↓
Game Engine (State + Rules)
        ↓
Infrastructure (Postgres, Redis, RabbitMQ)
```

### ⚔️ Laws of the Realm

- **State is law** — the world exists outside the agents  
- **Rules are absolute** — no “vibes-based combat”  
- **Agents are bounded** — structured actions only  
- **Events are recorded** — nothing is forgotten  
- **Humans are gods (optional)** — intervention is always possible  

---

## ⚙️ Tools of the Trade

| Layer | Tech |
|------|------|
| Backend | Python (FastAPI) |
| Frontend | React + TypeScript |
| Containers | Docker |
| Database | Postgres |
| Cache | Redis |
| Event Bus | RabbitMQ |
| Local LLM | LM Studio |
| Future LLM | Azure AI Foundry |

---

## 📜 The Grand Library (`/docs`)

| Scroll | Description |
|--------|------------|
| 01 | Product overview & vision |
| 02 | System architecture |
| 03 | Agent runtime |
| 04 | Game engine |
| 05 | UI & API |
| 06 | LLM integration |
| 07 | Data models |
| 08 | Delivery plan |
| 09 | Repo structure |
| 10 | Open questions |

---

## 🚀 How to Begin the Quest

1. Study the scrolls:
   - `02-system-architecture.md`
   - `04-game-engine.md`
   - `03-agent-runtime.md`

2. Forge the core:
   - Game state schema
   - Turn engine loop
   - Action validation system

3. Raise the world:
   - Docker Compose
   - Backend services
   - Frontend shell

## Local Startup

For the current scaffold:

```bash
docker compose up --build
python -m pytest packages/shared-schemas/tests
python -m pytest packages/shared-config/tests
python packages/shared-schemas/scripts/export_schemas.py
python packages/shared-config/scripts/run_migrations.py --database-url sqlite:///./dungeoncore.db
```

If you want the baseline Python contract checks as well:

```bash
python -m mypy packages/shared-schemas/src/shared_schemas
```

---

## 🧑‍🤝‍🧑 Roles at the Table

### 👀 Spectator
Observe the unfolding campaign in real time.

### 🎮 Player
Take control of a character — or replace an agent entirely.

### 🎛 Director (DM of DMs)
Pause time, inspect minds, bend reality.

---

## 💬 Voices Around the Table

Agents communicate through structured channels:

- 🗣 `in_character` — spoken in the world  
- 🧠 `table_talk` — tactical coordination  
- 🔒 `private_whisper` — secrets and schemes  
- 👁 `dm_notice` — hidden truths  

Conversation is:
- limited  
- structured  
- meaningful  

No endless tavern chatter. Decisions must be made.

---

## 🧩 Current Status

🟡 Early Stage — The dungeon is being carved.

Next milestone:

> **A playable encounter with multiple agents, a DM, and a full turn loop**

---

## 🐉 The Lore of the Repository

Commits are recorded as acts of legend:

```bash
feat: Roll initiative — implement turn engine
fix: Dispel a cursed state mutation
docs: Inscribe the communication protocol
```

Pull Requests are known as:

> **Sessions**

This is not optional.  
The lore must be respected.

---

## ⚠️ Sacred Rules

- The world state is **canonical**
- Agents **do not control reality**
- All actions are **validated**
- All changes are **event-driven**
- Memory is **curated, not infinite**
- Humans may **intervene at any time**

---

## 🔮 Future Prophecies

- Voice-driven campaigns  
- Persistent worlds  
- Multi-party interactions  
- Adaptive agent personalities  
- Live-streamed AI campaigns  

---

## 🧠 Final Words

DungeonCore is not about D&D.

It is about:

> **autonomous systems cooperating under constraint**

D&D just happens to be the perfect battlefield.

---

> *“Roll initiative.”*
