from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Protocol

from shared_config.coordination import RedisCoordinator
import logging

if TYPE_CHECKING:
    from shared_config.persistence import AIInvocationRepository

from shared_schemas.actions import ActionUnion, PlayerTurn
from shared_schemas.enums import ActionType, ActorRole, ControllerType, MessageChannel, ScenePhase
from shared_schemas.events import (
    ActionAwaitingHumanEvent,
    ActionAwaitingHumanPayload,
    ActionProposedEvent,
    ActionProposedPayload,
    ActionResolvedEvent,
    ActionResolvedPayload,
    ActionValidatedEvent,
    ActionValidatedPayload,
    DiceRollRecord,
    DiceRolledEvent,
    DiceRolledPayload,
    DiscussionClosedEvent,
    DiscussionOpenedEvent,
    DiscussionWindowPayload,
    MapUpdatedEvent,
    MapUpdatedPayload,
    MessageCreatedEvent,
    MessageCreatedPayload,
    NarrationEmittedEvent,
    NarrationEmittedPayload,
    SceneStartedEvent,
    SceneStartedPayload,
    StatePatchRecord,
    StateUpdatedEvent,
    StateUpdatedPayload,
    TurnEndedEvent,
    TurnEndedPayload,
)
from shared_schemas.state import GameState

from .fixtures.agent_configs import get_config_for_actor, DM_AGENT_CONFIG
from .human_interaction import HumanActionStore, OverrideStore, LastResolutionStore, ActionHistoryStore
from .trace_logger import TurnTraceLogger
from .service_integration import (
    ServiceClients,
    InvokeAgentRequest,
    ValidateActionRequest,
    ResolveActionRequest,
    CreateMessageRequest,
    apply_state_patches,
)
from .state_machine import PhaseContext, StateMachine, create_phase_context

logger = logging.getLogger(__name__)


def _compute_valid_path(
    state: GameState,
    start_x: int,
    start_y: int,
    target_x: int,
    target_y: int,
    max_steps: int = 8,
    stop_adjacent: bool = False,
) -> list[str]:
    """Compute a valid step-by-step path avoiding walls and doors.
    
    Uses greedy pathfinding - moves toward target while avoiding obstacles.
    Returns list of coordinate strings like ["4,5", "4,6", "5,6"].
    """
    if state.dungeon_map is None:
        return []
    
    dungeon_map = state.dungeon_map
    path: list[str] = []
    cx, cy = start_x, start_y
    visited = {(cx, cy)}
    
    for _ in range(max_steps):
        # Check if we've reached target (or adjacent if stop_adjacent)
        dist = max(abs(target_x - cx), abs(target_y - cy))
        if dist == 0 or (stop_adjacent and dist <= 1):
            break
        
        # Find best adjacent tile to move to
        candidates = []
        
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx == 0 and dy == 0:
                    continue
                nx, ny = cx + dx, cy + dy
                
                # Skip visited tiles to prevent loops
                if (nx, ny) in visited:
                    continue
                
                # Check bounds
                if not (0 <= nx < dungeon_map.width and 0 <= ny < dungeon_map.height):
                    continue
                
                tile = dungeon_map.tiles[ny][nx]
                
                # Check if walkable (revealed floor or difficult terrain)
                if not tile.revealed:
                    continue
                terrain = tile.terrain.value if hasattr(tile.terrain, 'value') else str(tile.terrain)
                if terrain in ("wall", "pit", "water_deep"):
                    continue
                # Skip closed doors for pathfinding (would need interact first)
                if terrain in ("door", "door_locked"):
                    continue
                
                # Calculate distance to target (Chebyshev)
                new_dist = max(abs(target_x - nx), abs(target_y - ny))
                candidates.append((new_dist, nx, ny))
        
        if not candidates:
            break  # No valid move found
        
        # Pick the candidate that gets closest to target
        candidates.sort(key=lambda c: c[0])
        _, nx, ny = candidates[0]
        
        visited.add((nx, ny))
        cx, cy = nx, ny
        path.append(f"{cx},{cy}")
    
    return path


def _get_valid_adjacent_tiles(state: GameState, x: int, y: int) -> list[str]:
    """Get list of valid adjacent tiles the actor can move to."""
    if state.dungeon_map is None:
        return []
    
    dungeon_map = state.dungeon_map
    valid_moves: list[str] = []
    
    for dx in [-1, 0, 1]:
        for dy in [-1, 0, 1]:
            if dx == 0 and dy == 0:
                continue
            nx, ny = x + dx, y + dy
            
            # Check bounds
            if not (0 <= nx < dungeon_map.width and 0 <= ny < dungeon_map.height):
                continue
            
            tile = dungeon_map.tiles[ny][nx]
            if not tile.revealed:
                continue
            
            terrain = tile.terrain.value if hasattr(tile.terrain, 'value') else str(tile.terrain)
            
            if terrain == "floor" or terrain == "difficult":
                valid_moves.append(f"({nx},{ny})")
    
    return valid_moves


class EventPublisher(Protocol):
    async def publish(self, event: object) -> None: ...


@dataclass
class TurnContext:
    """Holds state that persists across phases within a single turn."""
    proposed_action: ActionUnion | None = None
    validated_action: ActionUnion | None = None
    resolution_description: str = ""
    resolution_dice_rolls: list[DiceRollRecord] = field(default_factory=list)
    resolution_patches: list[StatePatchRecord] = field(default_factory=list)
    resolution_hit: bool | None = None
    resolution_damage: int | None = None


@dataclass
class TurnResult:
    success: bool
    final_state: GameState
    events: list[object] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


HUMAN_ACTION_TIMEOUT_SECONDS = 120


class TurnRunner:
    def __init__(
        self,
        state_machine: StateMachine,
        coordinator: RedisCoordinator | None = None,
        clients: ServiceClients | None = None,
        publisher: EventPublisher | None = None,
        human_action_store: HumanActionStore | None = None,
        override_store: OverrideStore | None = None,
        last_resolution_store: LastResolutionStore | None = None,
        action_history_store: ActionHistoryStore | None = None,
        trace_logger: TurnTraceLogger | None = None,
        ai_invocation_repo: "AIInvocationRepository | None" = None,
    ) -> None:
        self.state_machine = state_machine
        self.coordinator = coordinator
        self._clients = clients
        self.publisher = publisher
        self.human_action_store = human_action_store or HumanActionStore()
        self.override_store = override_store or OverrideStore()
        self.last_resolution_store = last_resolution_store or LastResolutionStore()
        self.action_history_store = action_history_store or ActionHistoryStore()
        self.trace_logger = trace_logger or TurnTraceLogger()
        self.ai_invocation_repo = ai_invocation_repo
        self._events: list[object] = []
        self._turn_context: TurnContext = TurnContext()

    @property
    def clients(self) -> ServiceClients | None:
        return self._clients

    @clients.setter
    def clients(self, value: ServiceClients | None) -> None:
        self._clients = value

    async def _emit_event(self, event: object) -> None:
        self._events.append(event)
        if self.publisher:
            await self.publisher.publish(event)

    def _record_ai_invocation(
        self,
        ctx: PhaseContext,
        request: InvokeAgentRequest,
        response: object,
        latency_ms: int,
    ) -> None:
        """Record an AI agent invocation to the database for tracking."""
        if self.ai_invocation_repo is None:
            return

        try:
            success = getattr(response, "success", False)
            error = getattr(response, "error", None)
            turn = getattr(response, "turn", None)
            trace = getattr(response, "trace", None)

            response_payload: dict = {}
            if turn is not None and hasattr(turn, "model_dump"):
                response_payload["turn"] = turn.model_dump(mode="json")
            if trace is not None:
                response_payload["trace"] = trace
            if error:
                response_payload["error"] = error

            record = {
                "id": str(uuid.uuid4()),
                "session_id": ctx.session_id,
                "turn_number": ctx.state.turn.turn_number,
                "phase": ctx.state.scene.phase.value if hasattr(ctx.state.scene.phase, "value") else str(ctx.state.scene.phase),
                "actor_id": request.actor_id,
                "actor_name": request.actor_name,
                "invocation_mode": request.invocation_mode,
                "model": trace.get("model") if trace else None,
                "prompt_tokens": trace.get("prompt_tokens") if trace else None,
                "completion_tokens": trace.get("completion_tokens") if trace else None,
                "latency_ms": latency_ms,
                "success": success,
                "error": error,
                "response_payload": response_payload,
                "created_at": datetime.now(timezone.utc),
            }
            self.ai_invocation_repo.append(record)
        except Exception as e:
            logger.warning("Failed to record AI invocation: %s", e)

    async def _invoke_agent_with_recording(
        self,
        ctx: PhaseContext,
        request: InvokeAgentRequest,
    ) -> "InvokeAgentResponse":
        """Invoke an agent and record the invocation for tracking."""
        from .service_integration import InvokeAgentResponse

        if self.clients is None:
            return InvokeAgentResponse(success=False, error="No service clients configured")

        start_time = time.monotonic()
        response = await self.clients.agent_runtime.invoke_agent(request)
        latency_ms = int((time.monotonic() - start_time) * 1000)

        self._record_ai_invocation(ctx, request, response, latency_ms)
        return response

    async def _emit_map_updated(self, ctx: PhaseContext, changes_count: int) -> None:
        """Emit a map.updated event after the DM modifies the dungeon map."""
        if ctx.state.dungeon_map is None:
            return
        event = MapUpdatedEvent(
            **self._create_event_base(ctx),
            payload=MapUpdatedPayload(
                map_name=ctx.state.dungeon_map.name,
                changes_count=changes_count,
                full_map_included=False,
                created_at=datetime.now(timezone.utc),
            ),
        )
        await self._emit_event(event)

    async def _emit_state_updated(self, ctx: PhaseContext, reason: str) -> None:
        """Emit a state.updated event with the full game state."""
        event = StateUpdatedEvent(
            **self._create_event_base(ctx),
            payload=StateUpdatedPayload(
                state=ctx.state,
                reason=reason,
                created_at=datetime.now(timezone.utc),
            ),
        )
        await self._emit_event(event)

    def _reveal_tiles_around_position(self, ctx: PhaseContext, x: int, y: int, radius: int = 5) -> PhaseContext:
        """Reveal tiles around a position (fog of war update after movement).
        
        Args:
            ctx: Current phase context
            x: X coordinate of the position
            y: Y coordinate of the position  
            radius: Radius of tiles to reveal (default 5 for typical vision range)
            
        Returns:
            Updated phase context with revealed tiles
        """
        dungeon_map = ctx.state.dungeon_map
        if dungeon_map is None:
            return ctx
        
        revealed_count = 0
        updated_tiles = [[tile for tile in row] for row in dungeon_map.tiles]
        
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                nx, ny = x + dx, y + dy
                if 0 <= nx < dungeon_map.width and 0 <= ny < dungeon_map.height:
                    tile = updated_tiles[ny][nx]
                    if not tile.revealed:
                        updated_tiles[ny][nx] = tile.model_copy(update={"revealed": True})
                        revealed_count += 1
        
        if revealed_count > 0:
            from shared_schemas.state import DungeonMap
            new_map = dungeon_map.model_copy(update={"tiles": updated_tiles})
            new_state = ctx.state.model_copy(update={"dungeon_map": new_map})
            logger.info("[fog_of_war] Revealed %d tiles around (%d, %d)", revealed_count, x, y)
            return PhaseContext(
                session_id=ctx.session_id,
                state=new_state,
                trace_id=ctx.trace_id,
                correlation_id=ctx.correlation_id,
                created_at=ctx.created_at,
                metadata=ctx.metadata,
            )
        
        return ctx

    def _create_event_base(self, ctx: PhaseContext) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "session_id": ctx.session_id,
            "turn_number": ctx.state.turn.turn_number,
            "trace_id": ctx.trace_id,
            "correlation_id": ctx.correlation_id,
            "created_at": datetime.now(timezone.utc),
        }

    def _get_recent_actions_for_actor(
        self, session_id: str, actor_id: str
    ) -> list[RecentActionRecord]:
        """Get recent actions for an actor to pass to the agent runtime."""
        from .human_interaction import RecentActionRecord as HumanRecentActionRecord
        from .service_integration import RecentActionRecord

        history_records = self.action_history_store.get_recent_actions(session_id, actor_id)
        return [
            RecentActionRecord(
                action_type=r.action_type,
                target_id=r.target_id,
                turn_number=r.turn_number,
            )
            for r in history_records
        ]

    def _update_phase_context(self, ctx: PhaseContext, new_state: GameState) -> PhaseContext:
        """Helper to create updated PhaseContext with new state."""
        return PhaseContext(
            session_id=ctx.session_id,
            state=new_state,
            trace_id=ctx.trace_id,
            correlation_id=ctx.correlation_id,
            created_at=ctx.created_at,
            metadata=ctx.metadata,
        )

    async def _fetch_recent_messages(self, ctx: PhaseContext, limit: int = 20):
        """Fetch recent messages from communication service for agent context."""
        from shared_schemas.messages import TableMessage
        messages: list[TableMessage] = []
        if self.clients:
            try:
                messages = await self.clients.communication.get_messages(
                    session_id=ctx.session_id,
                    viewer_id=None,
                    turn_number=None,
                )
                if len(messages) > limit:
                    messages = messages[-limit:]
            except Exception as e:
                logger.warning("[_fetch_recent_messages] Failed to fetch messages: %s", e)
        return messages

    async def handle_scene_intro(self, ctx: PhaseContext) -> PhaseContext:
        now = datetime.now(timezone.utc)
        event = SceneStartedEvent(
            **self._create_event_base(ctx),
            payload=SceneStartedPayload(
                scene_id=ctx.state.scene.scene_id,
                scene_name=ctx.state.scene.name,
                phase=ctx.state.scene.phase,
                active_actor_id=ctx.state.scene.active_actor_id,
                created_at=now,
            ),
        )
        await self._emit_event(event)

        if self.clients:
            # Generate dynamic map if needed and enabled
            if ctx.state.flags.get("generate_dynamic_map") and ctx.state.dungeon_map is None:
                ctx = await self._run_map_generation(ctx)

            await self._run_scene_opening(ctx)

        return await self.state_machine.transition_to(ctx, ScenePhase.DISCUSSION)

    async def _run_map_generation(self, ctx: PhaseContext) -> PhaseContext:
        """Have the DM generate a dynamic dungeon map using procedural tools."""
        if not self.clients:
            return ctx

        flags = ctx.state.flags
        genre = flags.get("story_genre", "classic_fantasy")
        themes_raw = flags.get("story_themes", "exploration,combat")
        themes = themes_raw.split(",") if isinstance(themes_raw, str) else themes_raw
        difficulty = flags.get("story_difficulty", "medium")
        map_complexity = flags.get("map_complexity", "medium")
        random_seed = flags.get("story_random_seed", 42)

        theme_desc = ", ".join(themes) if isinstance(themes, list) else str(themes)

        complexity_guidance = {
            "simple": "Create a small dungeon with 2-3 rooms ALL connected by corridors. Total size around 20x15 tiles. Every room must be reachable from the entrance.",
            "medium": "Create a medium dungeon with 4-6 rooms ALL connected by corridors. Total size around 30x20 tiles. Every room must be reachable from the entrance.",
            "complex": "Create a larger dungeon with 6-10 rooms ALL connected by corridors. Total size around 40x30 tiles. Every room must be reachable from the entrance.",
        }

        map_gen_prompt = f"""{DM_AGENT_CONFIG.system_prompt}

You are creating a UNIQUE dungeon map for a new adventure. Use the map generation tools to build the dungeon.

STORY CONTEXT:
- Genre: {genre.replace('_', ' ').title()}
- Themes: {theme_desc}
- Difficulty: {difficulty.title()}
- Random Seed: {random_seed} (use for variety)

MAP REQUIREMENTS:
{complexity_guidance.get(map_complexity, complexity_guidance['medium'])}

=== CRITICAL MAP STRUCTURE RULES ===

**CONNECTIVITY IS MANDATORY**: Every room MUST be reachable from the entrance. A player must be able to walk from the entrance to any room in the dungeon.

**PLAN BEFORE BUILDING**: Before calling any tools, mentally plan:
1. Where each room will be placed (x, y, width, height)
2. Which rooms connect to which other rooms
3. Where corridors will run between rooms
4. Where doors will be placed (on room walls where corridors meet them)

**DOORS MUST CONNECT TO CORRIDORS**:
- A door is an opening in a room's wall that leads to a corridor or another room
- NEVER place a door on a wall that has only solid wall on the other side
- When you place a door on a room's wall, you MUST ALSO create a corridor that reaches that door position
- Example: If room A has a door at position (10, 5), there must be a corridor with floor tiles that reaches (10, 5)

**CORRIDOR CONNECTION RULES**:
- Corridors connect rooms by carving floor tiles through walls
- connect_rooms starts at (from_x, from_y) and ends at (to_x, to_y)
- The corridor endpoint coordinates should be INSIDE or ON THE WALL of each room
- For a door on the EAST wall of a room at x=15: start corridor at x=15 (the door position)
- For a door on the SOUTH wall of a room at y=10: start corridor at y=10 (the door position)

**ROOM SPACING**:
- Leave at least 3 tiles between rooms for corridors
- Rooms should not overlap or share walls (unless intentionally merged)
- Position rooms so corridors can run between them without going out of bounds

**VALIDATION CHECKLIST** (verify mentally before finishing):
[ ] Every room has at least one door
[ ] Every door has a corridor connecting to it
[ ] All rooms form a connected graph (can reach any room from entrance)
[ ] No doors open into solid walls
[ ] No isolated/unreachable rooms

=== GENERATION STEPS ===

1. **PLAN**: Decide room positions, sizes, and connections (don't make tool calls yet)
2. **init_map**: Create the base map filled with walls
3. **generate_room**: Create rooms one by one. Add doors where corridors WILL connect
4. **connect_rooms**: Create corridors between rooms. Corridor endpoints must reach the doors
5. **populate_room**: Add themed content to rooms
6. **spawn_enemies**: Place enemies in rooms (NOT in the entrance room!)
7. **reveal_area**: Reveal the entrance room where players begin

**EXAMPLE LAYOUT** (coordinates are illustrative):
- Entrance room at (2, 2) size 6x6, with door on EAST wall at offset 2
- Corridor from (8, 4) to (12, 4) connecting entrance to next room
- Storage room at (12, 2) size 5x5, with door on WEST wall at offset 2

=== IMPORTANT RULES ===

- Reveal the entrance room AND the corridor leading from it (so players can start exploring)
- Call reveal_area twice if needed: once for the entrance room, once for the first corridor
- Keep distant rooms hidden (fog of war) - only reveal what's immediately accessible
- Match room themes to the adventure genre
- Create interesting, varied layouts - no two dungeons should look the same
- ALWAYS spawn at least 2-4 enemies in rooms other than the entrance
- Enemy types: goblin, goblin_shaman, skeleton, zombie, bandit, cultist, giant_spider, wolf
- Place enemies in rooms players will discover as they explore (not in the entrance!)

Respond with JSON after completing all tool calls:
{{"speech": "Brief description of the dungeon you created"}}"""

        logger.info("[map_generation] Generating dynamic map for session=%s", ctx.session_id)

        response = await self._invoke_agent_with_recording(
            ctx,
            InvokeAgentRequest(
                session_id=ctx.session_id,
                agent_id=DM_AGENT_CONFIG.agent_id,
                actor_id="dm",
                actor_name=DM_AGENT_CONFIG.name,
                role=DM_AGENT_CONFIG.role,
                goals=["Generate an interesting dungeon map", "Create a unique layout"],
                state=ctx.state,
                system_prompt=map_gen_prompt,
                temperature=0.8,
                invocation_mode="action_commit",
                resolution_summary=f"Generate dungeon map for: {genre} adventure",
            ),
        )

        if not response.success:
            raise RuntimeError(f"[map_generation] DM agent failed to generate map: {response.error}")

        logger.info("[map_generation] Map generation completed for session=%s", ctx.session_id)

        # Update ctx.state with the modified state from tool execution
        if response.state is None:
            raise RuntimeError(f"[map_generation] DM agent did not return updated state for session={ctx.session_id}")

        ctx = PhaseContext(
            session_id=ctx.session_id,
            state=response.state,
            trace_id=ctx.trace_id,
            correlation_id=ctx.correlation_id,
            created_at=ctx.created_at,
            metadata=ctx.metadata,
        )
        logger.info("[map_generation] Updated state with generated map")
        logger.info("[map_generation] NPCs in state after generation: %d", len(ctx.state.npcs))
        for npc_id, npc in ctx.state.npcs.items():
            logger.info("[map_generation] NPC: %s at (%s,%s)", npc.name, npc.position.x if npc.position else "?", npc.position.y if npc.position else "?")

        if ctx.state.dungeon_map is None:
            raise RuntimeError(f"[map_generation] Map was not created by DM agent for session={ctx.session_id}")

        # Place players in the entrance room
        ctx = self._place_players_in_entrance(ctx)

        # Log map details for debugging
        if ctx.state.dungeon_map:
            dm = ctx.state.dungeon_map
            revealed_count = sum(1 for row in dm.tiles for tile in row if tile.revealed)
            logger.info(
                "[map_generation] Map '%s' size %dx%d, revealed tiles: %d/%d",
                dm.name, dm.width, dm.height, revealed_count, dm.width * dm.height
            )

        await self._emit_map_updated(ctx, changes_count=1)
        
        # Emit full state update so frontend receives the map and NPCs immediately
        await self._emit_state_updated(ctx, "Map generated with enemies placed")

        return ctx

    def _place_players_in_entrance(self, ctx: PhaseContext) -> PhaseContext:
        """Place all player characters in the entrance room of the generated map."""
        from shared_schemas.state import Position

        dungeon_map = ctx.state.dungeon_map
        if not dungeon_map:
            logger.warning("[place_players] No map available")
            return ctx

        # Find entrance tiles by looking at tile labels (rooms are labeled like 'entrance-floor')
        entrance_tiles = []
        revealed_tiles = []
        
        for y, row in enumerate(dungeon_map.tiles):
            for x, tile in enumerate(row):
                if tile.label and "entrance" in tile.label.lower() and "floor" in tile.label.lower():
                    entrance_tiles.append((x, y))
                elif tile.revealed and tile.terrain.value == "floor":
                    revealed_tiles.append((x, y))
        
        # Use entrance tiles, or fall back to any revealed floor tiles
        spawn_tiles = entrance_tiles if entrance_tiles else revealed_tiles
        
        if not spawn_tiles:
            logger.warning("[place_players] No entrance or revealed floor tiles found")
            return ctx

        # Calculate center of the entrance/revealed area
        avg_x = sum(t[0] for t in spawn_tiles) // len(spawn_tiles)
        avg_y = sum(t[1] for t in spawn_tiles) // len(spawn_tiles)
        
        # Find the closest actual floor tile to the center
        def distance(tile):
            return abs(tile[0] - avg_x) + abs(tile[1] - avg_y)
        
        spawn_tiles_sorted = sorted(spawn_tiles, key=distance)
        
        # Update character positions
        updated_characters = {}
        
        for i, (actor_id, char) in enumerate(ctx.state.characters.items()):
            # Use different tiles for different characters, cycling if needed
            tile_idx = min(i, len(spawn_tiles_sorted) - 1)
            spawn_x, spawn_y = spawn_tiles_sorted[tile_idx]
            
            # Small offset to avoid stacking if we run out of tiles
            if i >= len(spawn_tiles_sorted) and i > 0:
                spawn_x += (i % 3) - 1
                spawn_y += (i // 3) % 2
            
            new_pos = Position(
                x=spawn_x,
                y=spawn_y,
                zone_id="entrance",
            )
            updated_char = char.model_copy(update={"position": new_pos})
            updated_characters[actor_id] = updated_char
            logger.info(
                "[place_players] Placed %s at (%d, %d)",
                char.name, new_pos.x, new_pos.y
            )

        # Create updated state with new character positions
        new_state = ctx.state.model_copy(update={"characters": updated_characters})
        
        ctx = PhaseContext(
            session_id=ctx.session_id,
            state=new_state,
            trace_id=ctx.trace_id,
            correlation_id=ctx.correlation_id,
            created_at=ctx.created_at,
            metadata=ctx.metadata,
        )
        
        # Reveal tiles around all player starting positions
        for actor_id, char in updated_characters.items():
            if char.position:
                ctx = self._reveal_tiles_around_position(
                    ctx, char.position.x, char.position.y, radius=5
                )
                logger.info(
                    "[place_players] Revealed tiles around %s at (%d, %d)",
                    char.name, char.position.x, char.position.y
                )
        
        return ctx

    async def _run_scene_opening(self, ctx: PhaseContext) -> None:
        """DM sets the scene and characters introduce themselves."""
        if not self.clients:
            return

        scene = ctx.state.scene
        characters = list(ctx.state.characters.values())
        npcs = list(ctx.state.npcs.values())
        flags = ctx.state.flags

        # Filter NPCs to only those visible to players (line of sight)
        # DM should only narrate about enemies players can actually see
        from .service_integration import get_visible_npcs_for_players
        visible_npcs = get_visible_npcs_for_players(ctx.state)
        
        npc_desc = ", ".join(f"{n.name} ({n.disposition})" for n in visible_npcs) if visible_npcs else "none visible yet"
        char_desc = ", ".join(f"{c.name} ({c.character_class})" for c in characters)

        # Extract story configuration from flags
        genre = flags.get("story_genre", "classic_fantasy")
        themes_raw = flags.get("story_themes", "exploration,combat")
        themes = themes_raw.split(",") if isinstance(themes_raw, str) else themes_raw
        difficulty = flags.get("story_difficulty", "medium")
        story_seed = flags.get("story_seed", "")
        random_seed = flags.get("story_random_seed", 0)

        # Build genre-specific tone guidance
        tone_guidance = self._get_genre_tone_guidance(genre)
        theme_desc = ", ".join(themes) if isinstance(themes, list) else str(themes)

        # Check if we're in dynamic story mode (story_genre was explicitly set)
        is_dynamic_story = flags.get("generate_dynamic_map") or story_seed

        # For dynamic stories, don't constrain DM with hardcoded MVP setting
        if is_dynamic_story:
            setting_context = f"""SETTING REQUIREMENTS:
- Create a completely original setting based on the genre and themes
- Location Type: {scene.location_name or 'A mysterious location fitting the genre'}
- Do NOT use the default goblin ambush scenario - create something unique
- The map and enemies present will guide what you describe"""
        else:
            setting_context = f"""SCENE CONTEXT:
- Scene Name: {scene.name}
- Location: {scene.location_name or 'Unknown Location'}
- Base Setting: {scene.summary}"""

        scene_prompt = f"""{DM_AGENT_CONFIG.system_prompt}

You are beginning a BRAND NEW D&D adventure. This is NOT a continuation - create a fresh, unique experience.

STORY CONFIGURATION:
- Genre: {genre.replace('_', ' ').title()}
- Themes: {theme_desc}
- Difficulty: {difficulty.title()}
- Story Seed: {story_seed or 'Create your own unique adventure hook'}
- Session Seed: {random_seed} (use this to inspire unique details)

{setting_context}

CAST:
- Player Characters: {char_desc}
- NPCs/Enemies Present: {npc_desc}

{tone_guidance}

NARRATION REQUIREMENTS:
1. Create a UNIQUE opening that could only belong to THIS session
2. Describe the environment with vivid sensory details (sights, sounds, smells, textures)
3. Establish mood and atmosphere matching the genre ({genre})
4. Weave in the themes: {theme_desc}
5. Introduce tension appropriate for {difficulty} difficulty
6. End with a compelling hook that demands player action
7. Make it memorable - this is the players' first impression of the adventure

DO NOT mention goblins, the ancient altar, or moss-covered corridors unless they fit YOUR unique story.

Respond with JSON:
{{"speech": "Your atmospheric opening narration (4-6 sentences)"}}"""

        response = await self._invoke_agent_with_recording(
            ctx,
            InvokeAgentRequest(
                session_id=ctx.session_id,
                agent_id=DM_AGENT_CONFIG.agent_id,
                actor_id="dm",
                actor_name=DM_AGENT_CONFIG.name,
                role=DM_AGENT_CONFIG.role,
                goals=DM_AGENT_CONFIG.goals,
                state=ctx.state,
                system_prompt=scene_prompt,
                temperature=0.8,
                invocation_mode="narration",
                resolution_summary=f"Opening scene: {scene.summary}",
            ),
        )

        if not response.success:
            raise RuntimeError(f"[scene_opening] DM agent failed: {response.error}")

        if not response.turn or not response.turn.speech:
            raise RuntimeError(f"[scene_opening] DM agent returned no speech for session={ctx.session_id}")

        narration_event = NarrationEmittedEvent(
            **self._create_event_base(ctx),
            payload=NarrationEmittedPayload(
                narrator_id="dm",
                text=response.turn.speech,
                created_at=datetime.now(timezone.utc),
            ),
        )
        await self._emit_event(narration_event)

        # Emit map.updated event after scene opening DM call (DM may have used map tools)
        if ctx.state.dungeon_map is not None:
            await self._emit_map_updated(ctx, changes_count=0)

    def _get_genre_tone_guidance(self, genre: str) -> str:
        """Get tone and style guidance based on story genre."""
        guidance_map = {
            "classic_fantasy": """TONE: Heroic and adventurous. Balance wonder with danger.
- Use classic fantasy imagery: torchlit corridors, ancient magic, noble quests
- Enemies are obstacles to overcome, not just threats
- There's always hope, even in dark moments""",

            "dark_fantasy": """TONE: Grim and foreboding. The world is dangerous and morally grey.
- Emphasize shadows, decay, and the weight of choices
- Magic has costs; power corrupts
- Trust is rare; betrayal is common
- Even victories feel hollow""",

            "horror": """TONE: Dread and unease. What lurks in the darkness?
- Build tension through what's NOT seen
- Emphasize vulnerability and isolation
- The environment itself feels hostile
- Something is deeply wrong here""",

            "mystery": """TONE: Intrigue and curiosity. Nothing is as it seems.
- Plant questions that demand answers
- Details matter - mention things that will be important later
- NPCs have secrets and hidden motives
- The truth is buried, but clues are everywhere""",

            "heroic": """TONE: Epic and inspiring. Heroes rise to impossible challenges.
- Grand stakes, noble causes
- Emphasize the characters' strength and potential
- Villains are powerful but can be defeated
- The world needs saving, and these are the ones to do it""",

            "survival": """TONE: Desperate and resource-aware. Every moment is a struggle.
- Emphasize scarcity and danger
- The environment is as much an enemy as any monster
- Difficult choices about what to save and what to sacrifice
- Relief is temporary; the next threat is always coming""",
        }
        return guidance_map.get(genre, guidance_map["classic_fantasy"])

    async def handle_discussion(self, ctx: PhaseContext) -> PhaseContext:
        """Handle discussion phase with agent reactions."""
        now = datetime.now(timezone.utc)

        if self.coordinator:
            self.coordinator.open_discussion_window(
                ctx.session_id,
                {"max_messages": ctx.state.turn.max_discussion_messages},
            )

        open_event = DiscussionOpenedEvent(
            **self._create_event_base(ctx),
            payload=DiscussionWindowPayload(
                scene_id=ctx.state.scene.scene_id,
                active_actor_id=ctx.state.scene.active_actor_id,
                max_messages=ctx.state.turn.max_discussion_messages,
                created_at=now,
            ),
        )
        await self._emit_event(open_event)

        new_turn = ctx.state.turn.model_copy(update={"discussion_open": True})
        new_state = ctx.state.model_copy(update={"turn": new_turn})
        ctx = self._update_phase_context(ctx, new_state)

        active_actor_id = ctx.state.scene.active_actor_id
        if self.clients and active_actor_id:
            await self._collect_discussion_messages(ctx, active_actor_id)

        if self.coordinator:
            self.coordinator.close_discussion_window(ctx.session_id)

        close_event = DiscussionClosedEvent(
            **self._create_event_base(ctx),
            payload=DiscussionWindowPayload(
                scene_id=ctx.state.scene.scene_id,
                active_actor_id=ctx.state.scene.active_actor_id,
                max_messages=ctx.state.turn.max_discussion_messages,
                created_at=datetime.now(timezone.utc),
            ),
        )
        await self._emit_event(close_event)

        new_turn = ctx.state.turn.model_copy(update={"discussion_open": False})
        new_state = ctx.state.model_copy(update={"turn": new_turn})
        ctx = self._update_phase_context(ctx, new_state)

        return await self.state_machine.transition_to(ctx, ScenePhase.ACTION_COMMIT)

    async def _collect_discussion_messages(self, ctx: PhaseContext, active_actor_id: str) -> None:
        """Collect discussion messages from non-active agent-controlled players."""
        if not self.clients:
            return

        await self.clients.communication.register_session(ctx.session_id, ctx.state)

        recent_messages = await self._fetch_recent_messages(ctx)

        non_active_characters = [
            char for char in ctx.state.characters.values()
            if char.actor_id != active_actor_id
            and char.alive
            and char.controller == ControllerType.AGENT
        ]

        for char in non_active_characters:
            config = get_config_for_actor(char.actor_id, char.name, char.role)

            response = await self._invoke_agent_with_recording(
                ctx,
                InvokeAgentRequest(
                    session_id=ctx.session_id,
                    agent_id=config.agent_id,
                    actor_id=char.actor_id,
                    actor_name=char.name,
                    role=config.role,
                    goals=config.goals,
                    state=ctx.state,
                    system_prompt=config.system_prompt,
                    temperature=config.temperature,
                    invocation_mode="discussion",
                    messages=recent_messages,
                ),
            )

            if response.success and response.turn:
                turn = response.turn
                if turn.speech:
                    await self._store_message(
                        ctx, char.actor_id, turn.speech, MessageChannel.IN_CHARACTER
                    )
                if turn.table_talk:
                    await self._store_message(
                        ctx, char.actor_id, turn.table_talk, MessageChannel.TABLE_TALK
                    )

    async def _store_message(
        self,
        ctx: PhaseContext,
        sender_id: str,
        text: str,
        channel: MessageChannel,
    ) -> None:
        """Store a message via communication service and emit event."""
        if not self.clients:
            return

        response = await self.clients.communication.create_message(
            CreateMessageRequest(
                session_id=ctx.session_id,
                scene_id=ctx.state.scene.scene_id,
                turn_number=ctx.state.turn.turn_number,
                phase=ctx.state.scene.phase,
                channel=channel,
                sender_id=sender_id,
                text=text,
            )
        )

        if response.success and response.message:
            event = MessageCreatedEvent(
                **self._create_event_base(ctx),
                payload=MessageCreatedPayload(
                    message=response.message,
                    created_at=datetime.now(timezone.utc),
                ),
            )
            await self._emit_event(event)

    async def handle_action_commit(self, ctx: PhaseContext) -> PhaseContext:
        """Request action from active player, validate, retry if needed."""
        active_actor_id = ctx.state.scene.active_actor_id
        if not active_actor_id:
            return await self.state_machine.transition_to(ctx, ScenePhase.RESOLUTION)

        actor = ctx.state.characters.get(active_actor_id)
        if not actor:
            return await self.state_machine.transition_to(ctx, ScenePhase.RESOLUTION)

        turn: PlayerTurn | None = None

        if actor.controller == ControllerType.HUMAN:
            turn = await self._await_human_action(ctx, actor.actor_id)
        elif self.clients:
            turn = await self._request_agent_action_with_validation(ctx, actor)

        if not turn:
            logger.error(
                "[action_commit] Agent returned no turn at all for actor=%s session=%s",
                active_actor_id, ctx.session_id,
            )
            return await self.state_machine.transition_to(ctx, ScenePhase.RESOLUTION)

        if not turn.action:
            logger.warning(
                "[action_commit] Agent returned turn with no action for actor=%s session=%s (speech=%s)",
                active_actor_id, ctx.session_id, bool(turn.speech),
            )

        self._turn_context.proposed_action = turn.action
        self._turn_context.validated_action = turn.action

        if turn.speech:
            await self._store_message(
                ctx, actor.actor_id, turn.speech, MessageChannel.IN_CHARACTER
            )
        if turn.table_talk:
            await self._store_message(
                ctx, actor.actor_id, turn.table_talk, MessageChannel.TABLE_TALK
            )

        return await self.state_machine.transition_to(ctx, ScenePhase.RESOLUTION)

    async def _await_human_action(self, ctx: PhaseContext, actor_id: str) -> PlayerTurn | None:
        """Wait for a human player to submit their action."""
        allowed_actions = [
            ActionType.ATTACK, ActionType.MOVE, ActionType.DEFEND,
            ActionType.INSPECT, ActionType.CAST_SPELL_BASIC, ActionType.MOVE_AND_ATTACK,
        ]

        awaiting_event = ActionAwaitingHumanEvent(
            **self._create_event_base(ctx),
            payload=ActionAwaitingHumanPayload(
                actor_id=actor_id,
                allowed_actions=allowed_actions,
                timeout_seconds=HUMAN_ACTION_TIMEOUT_SECONDS,
                created_at=datetime.now(timezone.utc),
            ),
        )
        await self._emit_event(awaiting_event)

        self.human_action_store.create_pending(ctx.session_id, actor_id)
        turn = await self.human_action_store.wait_for_action(
            ctx.session_id, timeout_seconds=HUMAN_ACTION_TIMEOUT_SECONDS
        )

        if turn and turn.action:
            await self._emit_action_proposed_event(ctx, actor_id, turn)

        return turn

    async def _request_agent_action_with_validation(
        self, ctx: PhaseContext, actor: object
    ) -> PlayerTurn | None:
        """Request action from an agent, validate, retry on failure."""
        if not self.clients:
            return None

        turn = await self._request_player_action(ctx, actor.actor_id, actor.name)

        if not turn:
            logger.error(
                "[action_validate] Agent runtime returned no turn for actor=%s session=%s",
                actor.actor_id, ctx.session_id,
            )
            return None

        # Log what we received from the agent
        action_type = turn.action.type.value if turn.action else "NO_ACTION"
        logger.info(
            "[action_validate] Received turn from agent: actor=%s action_type=%s has_speech=%s has_table_talk=%s",
            actor.actor_id, action_type, bool(turn.speech), bool(turn.table_talk),
        )
        
        # Log movement path details for debugging pathfinding issues
        if turn.action and hasattr(turn.action, 'movement_path') and turn.action.movement_path:
            logger.info(
                "[action_validate] Movement path proposed: actor=%s path=%s",
                actor.actor_id, turn.action.movement_path,
            )

        if not turn.action:
            logger.warning(
                "[action_validate] Agent returned speech-only turn (no action) for actor=%s",
                actor.actor_id,
            )
            return turn

        await self._emit_action_proposed_event(ctx, actor.actor_id, turn)

        validation = await self.clients.game_engine.validate_action(
            ValidateActionRequest(
                action=turn.action,
                actor_id=actor.actor_id,
                state=ctx.state,
            )
        )

        await self._emit_action_validated_event(
            ctx, actor.actor_id, validation.valid, turn.action, validation.errors
        )

        if validation.valid:
            logger.info(
                "[action_validate] Action validated successfully for actor=%s action_type=%s",
                actor.actor_id, turn.action.type.value if turn.action else "none",
            )
            return turn

        logger.warning(
            "[action_validate] First attempt failed validation for actor=%s errors=%s — retrying",
            actor.actor_id, validation.errors,
        )

        turn = await self._request_player_action_with_errors(
            ctx, actor.actor_id, actor.name, validation.errors
        )

        if not turn or not turn.action:
            logger.error(
                "[action_validate] Retry returned no action for actor=%s session=%s",
                actor.actor_id, ctx.session_id,
            )
            return turn

        validation = await self.clients.game_engine.validate_action(
            ValidateActionRequest(
                action=turn.action,
                actor_id=actor.actor_id,
                state=ctx.state,
            )
        )

        await self._emit_action_validated_event(
            ctx, actor.actor_id, validation.valid, turn.action, validation.errors
        )

        if not validation.valid:
            logger.error(
                "[action_validate] Retry also failed validation for actor=%s errors=%s — giving up",
                actor.actor_id, validation.errors,
            )
            return None

        return turn

    async def _request_player_action(
        self,
        ctx: PhaseContext,
        actor_id: str,
        actor_name: str,
    ) -> PlayerTurn | None:
        """Request an action from a player agent."""
        if not self.clients:
            return None

        actor = ctx.state.characters.get(actor_id)
        if not actor:
            return None

        config = get_config_for_actor(actor_id, actor_name, ActorRole.PLAYER)

        recent_messages = await self._fetch_recent_messages(ctx)

        recent_actions = self._get_recent_actions_for_actor(ctx.session_id, actor_id)

        response = await self._invoke_agent_with_recording(
            ctx,
            InvokeAgentRequest(
                session_id=ctx.session_id,
                agent_id=config.agent_id,
                actor_id=actor_id,
                actor_name=actor_name,
                role=config.role,
                goals=config.goals,
                state=ctx.state,
                system_prompt=config.system_prompt,
                temperature=config.temperature,
                invocation_mode="action_commit",
                messages=recent_messages,
                recent_actions=recent_actions,
            ),
        )

        if response.success and response.turn:
            return response.turn
        return None

    async def _request_player_action_with_errors(
        self,
        ctx: PhaseContext,
        actor_id: str,
        actor_name: str,
        errors: list[str],
    ) -> PlayerTurn | None:
        """Request action again, providing previous validation errors."""
        if not self.clients:
            return None

        actor = ctx.state.characters.get(actor_id)
        if not actor:
            return None

        config = get_config_for_actor(actor_id, actor_name, ActorRole.PLAYER)

        error_context = "\n".join(f"- {e}" for e in errors)

        # Build helpful position context for the retry
        position_hint = ""
        if actor.position:
            position_hint = f"\nYour current position: ({actor.position.x},{actor.position.y})"

        # Classify error types for targeted hints
        range_error = any("reach" in e.lower() or "range" in e.lower() for e in errors)
        path_format_error = any("coordinate" in e.lower() or "x,y" in e.lower() for e in errors)
        adjacency_error = any("not adjacent" in e.lower() for e in errors)
        terrain_error = any("impassable" in e.lower() or "wall" in e.lower() for e in errors)
        door_error = any("closed door" in e.lower() for e in errors)
        door_adjacency_error = any("must be adjacent to the door" in e.lower() for e in errors)
        budget_error = any("budget" in e.lower() or "cost" in e.lower() for e in errors)

        hints: list[str] = []
        
        # Path format error
        if path_format_error:
            hints.append(
                "CRITICAL: movement_path must use 'x,y' coordinate strings such as [\"3,9\", \"4,9\"]. "
                "Do NOT use names like 'corridor-entrance'. Use the numeric grid coordinates from the Map section."
            )
        
        # Adjacency error - agent is skipping tiles
        if adjacency_error:
            ax = actor.position.x if actor.position else 0
            ay = actor.position.y if actor.position else 0
            hints.append(
                f"**PATHFINDING ERROR**: Each step in movement_path must be ADJACENT to the previous position.\n"
                f"Adjacent means: within 1 tile (including diagonals).\n"
                f"You are at ({ax},{ay}). If you want to reach (4,6), you must walk step-by-step:\n"
                f"WRONG: [\"4,6\"] - this skips tiles!\n"
                f"RIGHT: [\"{ax},{ay+1}\", \"{ax},{ay+2}\", \"{ax},{ay+3}\"] - each step is 1 tile from the previous\n"
                f"Plan your path on the map: find a route where each coordinate is exactly 1 tile from the last."
            )
        
        # Terrain error - agent walking through walls
        if terrain_error:
            ax = actor.position.x if actor.position else 0
            ay = actor.position.y if actor.position else 0
            valid_adjacent = _get_valid_adjacent_tiles(ctx.state, ax, ay)
            valid_list = ', '.join(valid_adjacent) if valid_adjacent else "(none visible)"
            hints.append(
                f"**TERRAIN ERROR**: You tried to walk through a wall (#) or other impassable terrain.\n"
                f"Your position: ({ax},{ay})\n"
                f"VALID ADJACENT TILES you can walk to: {valid_list}\n\n"
                f"Map legend:\n"
                f"  . = floor (OK to walk)\n"
                f"  ~ = difficult terrain (OK but costs 2 movement)\n"
                f"  D = door (must be opened first!)\n"
                f"You CANNOT walk through:\n"
                f"  # = wall (BLOCKED)\n"
                f"  ? = unexplored (BLOCKED)\n"
                f"Pick one of the valid adjacent tiles above, or use 'defend' to stay in place."
            )
        
        # Door adjacency error - agent trying to interact with door from too far
        if door_adjacency_error:
            ax = actor.position.x if actor.position else 0
            ay = actor.position.y if actor.position else 0
            valid_adjacent = _get_valid_adjacent_tiles(ctx.state, ax, ay)
            valid_list = ', '.join(valid_adjacent) if valid_adjacent else "(none visible)"
            
            # Find the door they were trying to interact with and compute path
            for err in errors:
                if "door at" in err.lower():
                    # Extract coordinates from error like "door at (6,10)"
                    import re
                    match = re.search(r'\((\d+),(\d+)\)', err)
                    if match:
                        door_x, door_y = int(match.group(1)), int(match.group(2))
                        path_to_door = _compute_valid_path(ctx.state, ax, ay, door_x, door_y, max_steps=8, stop_adjacent=True)
                        if path_to_door:
                            path_str = ', '.join(f'"{p}"' for p in path_to_door)
                            hints.append(
                                f"**DOOR TOO FAR**: You tried to open a door at ({door_x},{door_y}) but you're not adjacent.\n"
                                f"Your position: ({ax},{ay})\n\n"
                                f"FIRST move closer to the door:\n"
                                f"  {{\"type\": \"move\", \"movement_path\": [{path_str}]}}\n\n"
                                f"THEN on your NEXT turn, open the door:\n"
                                f"  {{\"type\": \"interact\", \"target_id\": \"door:{door_x},{door_y}\", \"interaction_type\": \"open\"}}"
                            )
                        else:
                            hints.append(
                                f"**DOOR TOO FAR**: You tried to open a door at ({door_x},{door_y}) but you're not adjacent.\n"
                                f"Your position: ({ax},{ay})\n"
                                f"Move closer first. VALID ADJACENT TILES: {valid_list}"
                            )
                        break
        
        # Door error - agent needs to open door first (trying to walk through closed door)
        if door_error and not door_adjacency_error:
            ax = actor.position.x if actor.position else 0
            ay = actor.position.y if actor.position else 0
            valid_adjacent = _get_valid_adjacent_tiles(ctx.state, ax, ay)
            valid_list = ', '.join(valid_adjacent) if valid_adjacent else "(none visible)"
            
            # Find nearby door coordinates from the map tiles
            door_pos = None
            if ctx.state.dungeon_map:
                for dy in [-1, 0, 1]:
                    for dx in [-1, 0, 1]:
                        nx, ny = ax + dx, ay + dy
                        if 0 <= nx < ctx.state.dungeon_map.width and 0 <= ny < ctx.state.dungeon_map.height:
                            tile = ctx.state.dungeon_map.tiles[ny][nx]
                            terrain = tile.terrain.value if hasattr(tile.terrain, 'value') else str(tile.terrain)
                            if terrain in ("door", "door_locked") and not tile.door_open:
                                door_pos = (nx, ny)
                                break
                    if door_pos:
                        break
            
            door_target = f"door:{door_pos[0]},{door_pos[1]}" if door_pos else "door"
            
            hints.append(
                f"**DOOR ERROR**: You tried to walk through a closed door (D).\n"
                f"Your position: ({ax},{ay})\n\n"
                f"OPTION 1 - Open the door this turn:\n"
                f"  {{\"type\": \"interact\", \"target_id\": \"{door_target}\", \"interaction_type\": \"open\"}}\n"
                f"  (You can walk through it NEXT turn after opening)\n\n"
                f"OPTION 2 - Move somewhere else this turn:\n"
                f"  VALID ADJACENT TILES: {valid_list}\n"
                f"  Pick one of these to explore a different direction."
            )
        if range_error or budget_error:
            # Show the actor's current position and compute distances to all enemies
            enemy_info: list[str] = []
            ax = actor.position.x if actor.position else 0
            ay = actor.position.y if actor.position else 0
            closest_enemy = None
            closest_dist = 999
            for nid, npc in ctx.state.npcs.items():
                if npc.disposition == "hostile" and npc.alive and npc.hp > 0 and npc.position:
                    dx = abs(npc.position.x - ax)
                    dy = abs(npc.position.y - ay)
                    chebyshev = max(dx, dy)
                    steps_to_adjacent = chebyshev - 1
                    if chebyshev == 1:
                        action_hint = "→ use 'attack' (already adjacent!)"
                    else:
                        action_hint = f"→ use 'move_and_attack' with {steps_to_adjacent} step(s)"
                    enemy_info.append(
                        f"  - {npc.name} ({nid}) at ({npc.position.x},{npc.position.y}): "
                        f"DIST={chebyshev} {action_hint}"
                    )
                    if chebyshev < closest_dist:
                        closest_dist = chebyshev
                        closest_enemy = (nid, npc.name, npc.position.x, npc.position.y)
            enemy_list = "\n".join(enemy_info) if enemy_info else "  (no visible enemies)"

            # Build a concrete example path to the closest enemy using proper pathfinding
            example_path = ""
            if closest_enemy and closest_dist > 1:
                nid, nname, ex, ey = closest_enemy
                # Use the pathfinding function that avoids walls and doors
                computed_path = _compute_valid_path(
                    ctx.state, ax, ay, ex, ey, max_steps=8, stop_adjacent=True
                )
                if computed_path:
                    path_str = ", ".join(f'"{p}"' for p in computed_path)
                    example_path = (
                        f"\n\nCONCRETE EXAMPLE for {nname} ({nid}):\n"
                        f"  {{\"type\": \"move_and_attack\", \"movement_path\": [{path_str}], \"target_id\": \"{nid}\"}}"
                    )

            hints.append(
                f"YOUR POSITION: ({ax},{ay})\n\n"
                f"ENEMY DISTANCES (DIST=1 means adjacent, DIST>1 means NOT adjacent):\n{enemy_list}\n\n"
                f"RULE: If DIST=1, use 'attack'. If DIST>1, you MUST use 'move_and_attack'.\n"
                f"Your previous action used 'attack' on a target that was NOT adjacent (DIST>1). This is invalid.\n"
                f"Movement budget: 8 squares per turn.{example_path}"
            )

        hint_text = "\n\n".join(hints)

        retry_prompt = f"""{config.system_prompt}

IMPORTANT: Your previous action was INVALID and was rejected. You must choose a different valid action.

Validation errors:
{error_context}
{position_hint}

{hint_text}

Choose a different, valid action using proper x,y coordinates."""

        recent_messages = await self._fetch_recent_messages(ctx)
        recent_actions = self._get_recent_actions_for_actor(ctx.session_id, actor_id)

        response = await self._invoke_agent_with_recording(
            ctx,
            InvokeAgentRequest(
                session_id=ctx.session_id,
                agent_id=config.agent_id,
                actor_id=actor_id,
                actor_name=actor_name,
                role=config.role,
                goals=config.goals,
                state=ctx.state,
                system_prompt=retry_prompt,
                temperature=config.temperature,
                invocation_mode="action_commit",
                messages=recent_messages,
                recent_actions=recent_actions,
            ),
        )

        if response.success and response.turn:
            return response.turn
        return None

    async def _emit_action_proposed_event(
        self,
        ctx: PhaseContext,
        actor_id: str,
        turn: PlayerTurn,
    ) -> None:
        """Emit action proposed event."""
        event = ActionProposedEvent(
            **self._create_event_base(ctx),
            payload=ActionProposedPayload(
                actor_id=actor_id,
                turn=turn,
                created_at=datetime.now(timezone.utc),
            ),
        )
        await self._emit_event(event)

    async def _emit_action_validated_event(
        self,
        ctx: PhaseContext,
        actor_id: str,
        valid: bool,
        action: ActionUnion | None,
        errors: list[str],
    ) -> None:
        """Emit action validated event."""
        event = ActionValidatedEvent(
            **self._create_event_base(ctx),
            payload=ActionValidatedPayload(
                actor_id=actor_id,
                valid=valid,
                normalized_action=action,
                errors=errors,
                created_at=datetime.now(timezone.utc),
            ),
        )
        await self._emit_event(event)

    async def handle_resolution(self, ctx: PhaseContext) -> PhaseContext:
        """Resolve the validated action and apply state patches."""
        active_actor_id = ctx.state.scene.active_actor_id
        action = self._turn_context.validated_action
        
        action_type = action.type.value if action else "NO_ACTION"
        logger.info(
            "[resolution] Starting resolution: actor=%s action_type=%s session=%s",
            active_actor_id, action_type, ctx.session_id,
        )

        override_turn = self.override_store.consume_override(ctx.session_id)
        if override_turn and override_turn.action:
            action = override_turn.action
            self._turn_context.validated_action = action

        if not active_actor_id:
            logger.warning(
                "[resolution] Skipping resolution - no active actor: session=%s",
                ctx.session_id
            )
            return await self.state_machine.transition_to(ctx, ScenePhase.NARRATION)

        if not action:
            logger.warning(
                "[resolution] Skipping resolution - no action submitted by actor=%s session=%s. "
                "Agent may have returned speech-only turn.",
                active_actor_id, ctx.session_id
            )
            return await self.state_machine.transition_to(ctx, ScenePhase.NARRATION)

        if self.clients:
            resolution = await self.clients.game_engine.resolve_action(
                ResolveActionRequest(
                    action=action,
                    actor_id=active_actor_id,
                    state=ctx.state,
                )
            )

            if not resolution.success:
                action_type_str = action.type.value if hasattr(action, "type") else "unknown"
                logger.error(
                    "[resolution] Failed for actor=%s action=%s session=%s: %s",
                    active_actor_id, action_type_str, ctx.session_id, resolution.description,
                )
                self.trace_logger.log_error(ctx.session_id, f"Resolution failed: {resolution.description}")

                self._turn_context.resolution_description = resolution.description

                resolved_event = ActionResolvedEvent(
                    **self._create_event_base(ctx),
                    payload=ActionResolvedPayload(
                        actor_id=active_actor_id,
                        action_type=str(resolution.action_type.value),
                        success=False,
                        description=resolution.description,
                        dice_rolls=[],
                        state_patches=[],
                        hit=None,
                        damage=None,
                        created_at=datetime.now(timezone.utc),
                    ),
                )
                await self._emit_event(resolved_event)

                return await self.state_machine.transition_to(ctx, ScenePhase.NARRATION)

            self._turn_context.resolution_description = resolution.description
            self._turn_context.resolution_hit = resolution.hit
            self._turn_context.resolution_damage = resolution.damage

            dice_records = [
                DiceRollRecord(
                    die=roll.die,
                    value=roll.value,
                    modifier=roll.modifier,
                    total=roll.total,
                    created_at=datetime.now(timezone.utc),
                )
                for roll in resolution.dice_rolls
            ]
            self._turn_context.resolution_dice_rolls = dice_records

            if dice_records:
                dice_event = DiceRolledEvent(
                    **self._create_event_base(ctx),
                    payload=DiceRolledPayload(
                        actor_id=active_actor_id,
                        action_type=str(resolution.action_type.value),
                        rolls=dice_records,
                        created_at=datetime.now(timezone.utc),
                    ),
                )
                await self._emit_event(dice_event)

            patch_records = [
                StatePatchRecord(
                    patch_type=patch.patch_type,
                    target_id=patch.target_id,
                    field=patch.field,
                    old_value=patch.old_value,
                    new_value=patch.new_value,
                    created_at=datetime.now(timezone.utc),
                )
                for patch in resolution.state_patches
            ]
            self._turn_context.resolution_patches = patch_records

            resolved_event = ActionResolvedEvent(
                **self._create_event_base(ctx),
                payload=ActionResolvedPayload(
                    actor_id=active_actor_id,
                    action_type=str(resolution.action_type.value),
                    success=resolution.success,
                    description=resolution.description,
                    dice_rolls=dice_records,
                    state_patches=patch_records,
                    hit=resolution.hit,
                    damage=resolution.damage,
                    created_at=datetime.now(timezone.utc),
                ),
            )
            logger.info(
                "[resolution] SUCCESS - emitting action.resolved: actor=%s type=%s hit=%s damage=%s session=%s",
                active_actor_id, resolution.action_type.value, resolution.hit, resolution.damage, ctx.session_id
            )
            await self._emit_event(resolved_event)
            self.trace_logger.log_action_resolved(ctx.session_id, resolution.description)

            if resolution.state_patches:
                new_state = apply_state_patches(ctx.state, resolution.state_patches)
                ctx = self._update_phase_context(ctx, new_state)
                
                # Reveal fog-of-war around player after movement
                if resolution.action_type in (ActionType.MOVE, ActionType.MOVE_AND_ATTACK):
                    actor = ctx.state.characters.get(active_actor_id)
                    if actor and actor.position:
                        ctx = self._reveal_tiles_around_position(
                            ctx, actor.position.x, actor.position.y, radius=5
                        )
                
                # Emit state update so frontend sees position/HP changes immediately
                await self._emit_state_updated(ctx, f"Action resolved: {resolution.description}")

            ctx = self._check_objective_flags(ctx)

            actor_char = ctx.state.characters.get(active_actor_id)
            self.last_resolution_store.store(ctx.session_id, {
                "actor_id": active_actor_id,
                "actor_name": actor_char.name if actor_char else "Unknown",
                "description": resolution.description,
                "hit": resolution.hit,
                "damage": resolution.damage,
                "action_type": str(resolution.action_type.value),
            })

            # Record action in history for repetitive loop detection
            target_id = getattr(action, "target_id", None) or getattr(action, "location_id", None)
            self.action_history_store.record_action(
                session_id=ctx.session_id,
                actor_id=active_actor_id,
                action_type=str(resolution.action_type.value),
                target_id=target_id,
                turn_number=ctx.state.turn.turn_number,
            )

        return await self.state_machine.transition_to(ctx, ScenePhase.NARRATION)

    async def handle_narration(self, ctx: PhaseContext) -> PhaseContext:
        """Generate DM narration for the resolved action."""
        active_actor_id = ctx.state.scene.active_actor_id

        if self.clients and active_actor_id:
            actor = ctx.state.characters.get(active_actor_id)
            actor_name = actor.name if actor else "Unknown"

            resolution_summary = self._build_resolution_summary(actor_name, ctx)
            recent_messages = await self._fetch_recent_messages(ctx)

            response = await self._invoke_agent_with_recording(
                ctx,
                InvokeAgentRequest(
                    session_id=ctx.session_id,
                    agent_id=DM_AGENT_CONFIG.agent_id,
                    actor_id="dm",
                    actor_name=DM_AGENT_CONFIG.name,
                    role=DM_AGENT_CONFIG.role,
                    goals=DM_AGENT_CONFIG.goals,
                    state=ctx.state,
                    system_prompt=DM_AGENT_CONFIG.system_prompt,
                    temperature=DM_AGENT_CONFIG.temperature,
                    invocation_mode="narration",
                    resolution_summary=resolution_summary,
                    messages=recent_messages,
                ),
            )

            if not response.success:
                logger.error(
                    "[narration] DM agent failed for session=%s: %s",
                    ctx.session_id, response.error,
                )
            elif not response.turn or not response.turn.speech:
                logger.warning(
                    "[narration] DM agent returned no speech for session=%s (turn=%s)",
                    ctx.session_id, response.turn,
                )

            narration_text = None
            if response.success and response.turn and response.turn.speech:
                narration_text = response.turn.speech

            if narration_text:
                narration_event = NarrationEmittedEvent(
                    **self._create_event_base(ctx),
                    payload=NarrationEmittedPayload(
                        narrator_id="dm",
                        text=narration_text,
                        created_at=datetime.now(timezone.utc),
                    ),
                )
                await self._emit_event(narration_event)
                self.trace_logger.log_narration(ctx.session_id, narration_text)

            # Emit map.updated event after narration (DM may have used map tools)
            if ctx.state.dungeon_map is not None:
                await self._emit_map_updated(ctx, changes_count=0)

        return await self.state_machine.transition_to(ctx, ScenePhase.REACTION)

    def _check_objective_flags(self, ctx: PhaseContext) -> PhaseContext:
        """Auto-update objective flags based on game state."""
        flags = dict(ctx.state.flags)
        updated = False

        if "corridor_cleared" in flags and not flags["corridor_cleared"]:
            all_hostile_dead = all(
                (not npc.alive or npc.hp <= 0)
                for npc in ctx.state.npcs.values()
                if npc.disposition == "hostile"
            )
            if all_hostile_dead:
                flags["corridor_cleared"] = True
                updated = True
                logger.info("[objectives] corridor_cleared flag set to True for session=%s", ctx.session_id)

        if updated:
            new_state = ctx.state.model_copy(update={"flags": flags})

            objectives = list(new_state.objectives)
            for i, obj in enumerate(objectives):
                if obj.objective_id == "obj-clear-corridor" and flags.get("corridor_cleared") and obj.status == "active":
                    objectives[i] = obj.model_copy(update={"status": "completed"})
                    logger.info("[objectives] obj-clear-corridor completed for session=%s", ctx.session_id)

            new_state = new_state.model_copy(update={"objectives": objectives})
            ctx = self._update_phase_context(ctx, new_state)

        return ctx

    def _build_resolution_summary(self, actor_name: str, ctx: PhaseContext | None = None) -> str:
        """Build a summary of the resolution for the DM to narrate."""
        parts = [
            "=== NARRATION INSTRUCTIONS ===",
            f"NARRATE ONLY {actor_name.upper()}'S ACTION BELOW.",
            "DO NOT narrate actions by any other character.",
            "DO NOT invent attacks, damage, or events not listed here.",
            "",
            "=== WHAT ACTUALLY HAPPENED ===",
            f"Active Actor: {actor_name} (ONLY this character acts)",
        ]

        action = self._turn_context.validated_action
        if action:
            parts.append(f"Action Taken: {action.type.value}")
            if hasattr(action, "target_id") and action.target_id:
                parts.append(f"Target: {action.target_id}")
            if hasattr(action, "movement_path") and action.movement_path:
                parts.append(f"Movement Path: {' -> '.join(action.movement_path)}")
                # Include explicit starting and ending positions from state patches
                # to avoid DM confabulating incorrect positions

        if self._turn_context.resolution_dice_rolls:
            rolls_str = ", ".join(
                f"{r.die}={r.value}+{r.modifier}={r.total}"
                for r in self._turn_context.resolution_dice_rolls
            )
            parts.append(f"Dice Rolled: {rolls_str}")

        if self._turn_context.resolution_hit is not None:
            hit_text = "HIT - attack connects!" if self._turn_context.resolution_hit else "MISS - attack fails!"
            parts.append(f"Attack Result: {hit_text}")

        if self._turn_context.resolution_damage is not None:
            parts.append(f"Damage Dealt: {self._turn_context.resolution_damage} HP")
        else:
            parts.append("Damage Dealt: NONE (no combat occurred)")

        if self._turn_context.resolution_description:
            parts.append(f"Mechanical Result: {self._turn_context.resolution_description}")

        # State changes - highlight position changes explicitly for accurate narration
        for patch in self._turn_context.resolution_patches:
            if patch.field == "position":
                # Extract coordinates more clearly for the DM
                old_pos = patch.old_value
                new_pos = patch.new_value
                parts.append(f"POSITION CHANGE: {patch.target_id} moved from {old_pos} to {new_pos}")
            else:
                parts.append(f"State Change: {patch.target_id}.{patch.field}: {patch.old_value} -> {patch.new_value}")

        parts.append("")
        parts.append("=== YOUR TASK ===")
        parts.append(f"Describe {actor_name}'s action in 2-3 cinematic sentences.")
        parts.append("Include ONLY events from the resolution above. NO extra combat or actions.")

        return "\n".join(parts)

    async def rerun_narration(self, ctx: PhaseContext, resolution_data: dict) -> str:
        """Re-run DM narration from stored resolution data (director override)."""
        if not self.clients:
            return "No agent runtime available for narration."

        actor_name = resolution_data.get("actor_name", "Unknown")
        description = resolution_data.get("description", "Action resolved.")
        hit = resolution_data.get("hit")
        damage = resolution_data.get("damage")
        action_type = resolution_data.get("action_type", "unknown")

        summary_parts = [f"Actor: {actor_name}", f"Action: {action_type}", f"Result: {description}"]
        if hit is not None:
            summary_parts.append(f"Hit: {'Yes' if hit else 'No'}")
        if damage is not None:
            summary_parts.append(f"Damage: {damage}")

        resolution_summary = "\n".join(summary_parts)

        response = await self._invoke_agent_with_recording(
            ctx,
            InvokeAgentRequest(
                session_id=ctx.session_id,
                agent_id=DM_AGENT_CONFIG.agent_id,
                actor_id="dm",
                actor_name=DM_AGENT_CONFIG.name,
                role=DM_AGENT_CONFIG.role,
                goals=DM_AGENT_CONFIG.goals,
                state=ctx.state,
                system_prompt=DM_AGENT_CONFIG.system_prompt,
                temperature=DM_AGENT_CONFIG.temperature,
                invocation_mode="narration",
                resolution_summary=resolution_summary,
            ),
        )

        if not response.success or not response.turn or not response.turn.speech:
            error = response.error or "No narration produced"
            logger.error("[rerun_narration] DM agent failed for session=%s: %s", ctx.session_id, error)
            return f"Narration failed: {error}"

        narration_text = response.turn.speech

        narration_event = NarrationEmittedEvent(
            **self._create_event_base(ctx),
            payload=NarrationEmittedPayload(
                narrator_id="dm",
                text=narration_text,
                created_at=datetime.now(timezone.utc),
            ),
        )
        await self._emit_event(narration_event)

        return narration_text

    async def handle_reaction(self, ctx: PhaseContext) -> PhaseContext:
        """Collect brief reactions from non-active characters after the narration."""
        if not self.clients:
            return await self.state_machine.transition_to(ctx, ScenePhase.TURN_END)

        active_actor_id = ctx.state.scene.active_actor_id
        recent_messages = await self._fetch_recent_messages(ctx)

        reacting_characters = [
            char for char in ctx.state.characters.values()
            if char.actor_id != active_actor_id
            and char.alive
            and char.hp > 0
            and char.controller == ControllerType.AGENT
        ]

        for char in reacting_characters:
            config = get_config_for_actor(char.actor_id, char.name, char.role)

            response = await self._invoke_agent_with_recording(
                ctx,
                InvokeAgentRequest(
                    session_id=ctx.session_id,
                    agent_id=config.agent_id,
                    actor_id=char.actor_id,
                    actor_name=char.name,
                    role=config.role,
                    goals=config.goals,
                    state=ctx.state,
                    system_prompt=config.system_prompt,
                    temperature=config.temperature,
                    invocation_mode="reaction",
                    messages=recent_messages,
                ),
            )

            if not response.success:
                logger.warning(
                    "[reaction] Agent failed for actor=%s: %s",
                    char.actor_id, response.error,
                )
                continue

            if response.turn and response.turn.speech:
                await self._store_message(
                    ctx, char.actor_id, response.turn.speech, MessageChannel.IN_CHARACTER,
                )

        return await self.state_machine.transition_to(ctx, ScenePhase.TURN_END)

    async def handle_turn_end(self, ctx: PhaseContext) -> PhaseContext:
        now = datetime.now(timezone.utc)

        characters = list(ctx.state.characters.values())
        current_actor_id = ctx.state.scene.active_actor_id

        next_actor_id: str | None = None
        if characters:
            if current_actor_id:
                current_index = next(
                    (i for i, c in enumerate(characters) if c.actor_id == current_actor_id),
                    -1,
                )
                next_index = (current_index + 1) % len(characters)
            else:
                next_index = 0
            next_actor_id = characters[next_index].actor_id

        event = TurnEndedEvent(
            **self._create_event_base(ctx),
            payload=TurnEndedPayload(
                actor_id=current_actor_id or "",
                next_actor_id=next_actor_id,
                phase=ctx.state.scene.phase,
                created_at=now,
            ),
        )
        await self._emit_event(event)

        new_turn_number = ctx.state.turn.turn_number + 1
        new_round = ctx.state.turn.round_number
        if next_actor_id and characters and next_actor_id == characters[0].actor_id:
            new_round += 1

        new_turn = ctx.state.turn.model_copy(
            update={
                "turn_number": new_turn_number,
                "round_number": new_round,
                "active_actor_id": next_actor_id,
                "remaining_discussion_messages": ctx.state.turn.max_discussion_messages,
            }
        )
        new_scene = ctx.state.scene.model_copy(
            update={
                "turn_number": new_turn_number,
                "active_actor_id": next_actor_id,
            }
        )
        new_state = ctx.state.model_copy(update={"turn": new_turn, "scene": new_scene})

        ctx = self._update_phase_context(ctx, new_state)

        self._turn_context = TurnContext()

        return await self.state_machine.transition_to(ctx, ScenePhase.DISCUSSION)

    def _build_context_summary(self, ctx: PhaseContext) -> str:
        parts = [f"Scene: {ctx.state.scene.name}"]
        for char in ctx.state.characters.values():
            parts.append(f"  {char.name}: HP {char.hp}/{char.max_hp}")
        for npc in ctx.state.npcs.values():
            parts.append(f"  {npc.name}: HP {npc.hp}/{npc.max_hp}")
        return "\n".join(parts)

    async def run_turn(self, ctx: PhaseContext) -> TurnResult:
        self._events = []
        errors: list[str] = []

        self.trace_logger.start_turn(
            session_id=ctx.session_id,
            turn_number=ctx.state.turn.turn_number,
            active_actor_id=ctx.state.scene.active_actor_id,
            context_summary=self._build_context_summary(ctx),
        )

        if self.coordinator:
            lock_acquired = self.coordinator.acquire_session_lock(ctx.session_id, owner="turn_runner")
            if not lock_acquired:
                self.trace_logger.log_error(ctx.session_id, "Failed to acquire session lock")
                self.trace_logger.finalize(ctx.session_id)
                return TurnResult(
                    success=False,
                    final_state=ctx.state,
                    events=[],
                    errors=["Failed to acquire session lock"],
                )

        try:
            if self.coordinator:
                self.coordinator.set_active_turn(
                    ctx.session_id,
                    {"turn_number": ctx.state.turn.turn_number, "active_actor_id": ctx.state.scene.active_actor_id or ""},
                )

            phase_handlers = {
                ScenePhase.SCENE_INTRO: self.handle_scene_intro,
                ScenePhase.DISCUSSION: self.handle_discussion,
                ScenePhase.ACTION_COMMIT: self.handle_action_commit,
                ScenePhase.RESOLUTION: self.handle_resolution,
                ScenePhase.NARRATION: self.handle_narration,
                ScenePhase.REACTION: self.handle_reaction,
                ScenePhase.TURN_END: self.handle_turn_end,
            }

            current_phase = ctx.state.scene.phase
            handler = phase_handlers.get(current_phase)

            if handler:
                self.trace_logger.log_phase(ctx.session_id, current_phase.value)
                ctx = await handler(ctx)

            self.trace_logger.finalize(ctx.session_id)
            return TurnResult(
                success=True,
                final_state=ctx.state,
                events=self._events.copy(),
                errors=errors,
            )

        except Exception as e:
            self.trace_logger.log_error(ctx.session_id, str(e))
            self.trace_logger.finalize(ctx.session_id)
            logger.error("[run_turn] Phase handler failed: %s", e, exc_info=True)
            raise  # Re-raise to surface errors instead of swallowing them

        finally:
            if self.coordinator:
                self.coordinator.clear_active_turn(ctx.session_id)
                self.coordinator.release_session_lock(ctx.session_id)

    async def run_full_turn_cycle(self, ctx: PhaseContext) -> TurnResult:
        """Run through all phases of a complete turn."""
        self._events = []
        self._turn_context = TurnContext()
        errors: list[str] = []

        self.trace_logger.start_turn(
            session_id=ctx.session_id,
            turn_number=ctx.state.turn.turn_number,
            active_actor_id=ctx.state.scene.active_actor_id,
            context_summary=self._build_context_summary(ctx),
        )

        if self.coordinator:
            lock_acquired = self.coordinator.acquire_session_lock(ctx.session_id, owner="turn_runner")
            if not lock_acquired:
                self.trace_logger.log_error(ctx.session_id, "Failed to acquire session lock")
                self.trace_logger.finalize(ctx.session_id)
                return TurnResult(
                    success=False,
                    final_state=ctx.state,
                    events=[],
                    errors=["Failed to acquire session lock"],
                )

        try:
            phases_in_order = [
                (ScenePhase.SCENE_INTRO, self.handle_scene_intro),
                (ScenePhase.DISCUSSION, self.handle_discussion),
                (ScenePhase.ACTION_COMMIT, self.handle_action_commit),
                (ScenePhase.RESOLUTION, self.handle_resolution),
                (ScenePhase.NARRATION, self.handle_narration),
                (ScenePhase.REACTION, self.handle_reaction),
                (ScenePhase.TURN_END, self.handle_turn_end),
            ]

            for phase, handler in phases_in_order:
                if ctx.state.scene.phase == phase:
                    self.trace_logger.log_phase(ctx.session_id, phase.value)
                    ctx = await handler(ctx)

            self.trace_logger.finalize(ctx.session_id)
            return TurnResult(
                success=True,
                final_state=ctx.state,
                events=self._events.copy(),
                errors=errors,
            )

        except Exception as e:
            self.trace_logger.log_error(ctx.session_id, str(e))
            self.trace_logger.finalize(ctx.session_id)
            logger.error("[run_full_turn_cycle] Turn cycle failed: %s", e, exc_info=True)
            raise  # Re-raise to surface errors instead of swallowing them

        finally:
            if self.coordinator:
                self.coordinator.release_session_lock(ctx.session_id)


def create_turn_runner(
    coordinator: RedisCoordinator | None = None,
    clients: ServiceClients | None = None,
    publisher: EventPublisher | None = None,
    human_action_store: HumanActionStore | None = None,
    override_store: OverrideStore | None = None,
    last_resolution_store: LastResolutionStore | None = None,
    trace_logger: TurnTraceLogger | None = None,
    ai_invocation_repo: "AIInvocationRepository | None" = None,
) -> TurnRunner:
    state_machine = StateMachine()
    return TurnRunner(
        state_machine=state_machine,
        coordinator=coordinator,
        clients=clients,
        publisher=publisher,
        human_action_store=human_action_store,
        override_store=override_store,
        last_resolution_store=last_resolution_store,
        trace_logger=trace_logger,
        ai_invocation_repo=ai_invocation_repo,
    )
