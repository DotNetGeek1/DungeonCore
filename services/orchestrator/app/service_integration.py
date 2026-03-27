"""Service integration layer for orchestrator to communicate with downstream services."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

import httpx

logger = logging.getLogger(__name__)

from shared_schemas.actions import ActionUnion, PlayerTurn
from shared_schemas.enums import ActionType, ActorRole, MessageChannel, ScenePhase
from shared_schemas.messages import TableMessage
from shared_schemas.state import GameState, Position


@dataclass
class RecentActionRecord:
    """Record of a recent action taken by an agent."""
    action_type: str
    target_id: str | None
    turn_number: int


@dataclass
class InvokeAgentRequest:
    session_id: str
    agent_id: str
    actor_id: str
    actor_name: str
    role: ActorRole
    goals: list[str]
    state: GameState
    system_prompt: str | None = None
    temperature: float = 0.4
    invocation_mode: str | None = None
    resolution_summary: str | None = None
    messages: list[TableMessage] = field(default_factory=list)
    recent_actions: list[RecentActionRecord] = field(default_factory=list)


@dataclass
class InvokeAgentResponse:
    success: bool
    turn: PlayerTurn | None = None
    trace: dict | None = None
    error: str | None = None
    state: GameState | None = None  # Updated state after tool execution


@dataclass
class ValidateActionRequest:
    action: ActionUnion
    actor_id: str
    state: GameState


@dataclass
class ValidateActionResponse:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ResolveActionRequest:
    action: ActionUnion
    actor_id: str
    state: GameState
    seed: int | None = None


@dataclass
class StatePatch:
    patch_type: str
    target_id: str
    field: str
    old_value: object
    new_value: object


@dataclass
class DiceRoll:
    die: str
    value: int
    modifier: int
    total: int


@dataclass
class ResolveActionResponse:
    success: bool
    action_type: ActionType
    description: str
    dice_rolls: list[DiceRoll] = field(default_factory=list)
    state_patches: list[StatePatch] = field(default_factory=list)
    hit: bool | None = None
    damage: int | None = None


@dataclass
class CreateMessageRequest:
    session_id: str
    scene_id: str
    turn_number: int
    phase: ScenePhase
    channel: MessageChannel
    sender_id: str
    text: str
    recipient_ids: list[str] = field(default_factory=list)


@dataclass
class CreateMessageResponse:
    success: bool
    message: TableMessage | None = None
    error: str | None = None


class AgentRuntimeClient:
    """HTTP client for agent-runtime service."""

    def __init__(self, base_url: str, http_client: httpx.AsyncClient) -> None:
        self.base_url = base_url.rstrip("/")
        self.http_client = http_client

    async def invoke_agent(self, request: InvokeAgentRequest) -> InvokeAgentResponse:
        """Invoke an agent to generate a PlayerTurn."""
        try:
            payload = {
                "session_id": request.session_id,
                "agent_id": request.agent_id,
                "actor_id": request.actor_id,
                "actor_name": request.actor_name,
                "role": request.role.value,
                "goals": request.goals,
                "state": request.state.model_dump(mode="json"),
            }
            if request.system_prompt:
                payload["system_prompt"] = request.system_prompt
            payload["temperature"] = request.temperature
            if request.invocation_mode:
                payload["invocation_mode"] = request.invocation_mode
            if request.resolution_summary:
                payload["resolution_summary"] = request.resolution_summary
            if request.messages:
                payload["messages"] = [m.model_dump(mode="json") for m in request.messages]
            if request.recent_actions:
                payload["recent_actions"] = [
                    {"action_type": ra.action_type, "target_id": ra.target_id, "turn_number": ra.turn_number}
                    for ra in request.recent_actions
                ]

            response = await self.http_client.post(
                f"{self.base_url}/invoke",
                json=payload,
                timeout=60.0,
            )
            response.raise_for_status()
            data = response.json()

            turn = None
            if data.get("turn"):
                turn = PlayerTurn.model_validate(data["turn"])

            updated_state = None
            if data.get("state"):
                updated_state = GameState.model_validate(data["state"])

            return InvokeAgentResponse(
                success=data.get("success", False),
                turn=turn,
                trace=data.get("trace"),
                error=data.get("error"),
                state=updated_state,
            )
        except httpx.HTTPStatusError as e:
            body = e.response.text[:500]
            logger.error(
                "[invoke_agent] HTTP %d from agent-runtime for actor=%s: %s",
                e.response.status_code, request.actor_id, body,
            )
            return InvokeAgentResponse(
                success=False,
                error=f"HTTP error {e.response.status_code}: {body[:200]}",
            )
        except Exception as e:
            logger.error("[invoke_agent] Error for actor=%s: %s", request.actor_id, e, exc_info=True)
            return InvokeAgentResponse(
                success=False,
                error=f"Agent runtime error: {str(e)}",
            )

    async def invoke_agent_streaming(
        self,
        request: InvokeAgentRequest,
        on_token: Callable[[str, str], Awaitable[None]] | None = None,
    ) -> InvokeAgentResponse:
        """Invoke an agent with SSE token streaming. on_token(actor_id, token)."""
        if on_token is None:
            return await self.invoke_agent(request)

        try:
            payload = {
                "session_id": request.session_id,
                "agent_id": request.agent_id,
                "actor_id": request.actor_id,
                "actor_name": request.actor_name,
                "role": request.role.value,
                "goals": request.goals,
                "state": request.state.model_dump(mode="json"),
            }
            if request.system_prompt:
                payload["system_prompt"] = request.system_prompt
            payload["temperature"] = request.temperature
            if request.invocation_mode:
                payload["invocation_mode"] = request.invocation_mode
            if request.resolution_summary:
                payload["resolution_summary"] = request.resolution_summary
            if request.messages:
                payload["messages"] = [m.model_dump(mode="json") for m in request.messages]
            if request.recent_actions:
                payload["recent_actions"] = [
                    {"action_type": ra.action_type, "target_id": ra.target_id, "turn_number": ra.turn_number}
                    for ra in request.recent_actions
                ]

            turn = None
            async with self.http_client.stream(
                "POST", f"{self.base_url}/invoke-stream",
                json=payload, timeout=180.0,
            ) as response:
                response.raise_for_status()
                buffer = ""
                async for chunk in response.aiter_text():
                    buffer += chunk
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            logger.warning("[invoke_stream] Unparseable SSE line: %.200s", data_str)
                            continue

                        if data.get("type") == "token":
                            await on_token(request.actor_id, data.get("token", ""))
                        elif data.get("type") == "result":
                            if data.get("turn"):
                                turn = PlayerTurn.model_validate(data["turn"])
                            updated_state = None
                            if data.get("state"):
                                updated_state = GameState.model_validate(data["state"])
                            error = data.get("error")
                            if error:
                                logger.error(
                                    "[invoke_stream] Agent returned error for actor=%s: %s",
                                    request.actor_id, error,
                                )
                            return InvokeAgentResponse(
                                success=data.get("success", False),
                                turn=turn,
                                error=error,
                                state=updated_state,
                            )
                        elif data.get("type") == "error":
                            logger.error(
                                "[invoke_stream] SSE error event for actor=%s: %s",
                                request.actor_id, data.get("error"),
                            )
                            updated_state = None
                            if data.get("state"):
                                updated_state = GameState.model_validate(data["state"])
                            return InvokeAgentResponse(
                                success=False,
                                error=data.get("error", "Unknown streaming error"),
                                state=updated_state,
                            )

            if turn:
                return InvokeAgentResponse(success=True, turn=turn)

            logger.error(
                "[invoke_stream] Stream ended without result event for actor=%s agent=%s mode=%s",
                request.actor_id, request.agent_id, request.invocation_mode,
            )
            return InvokeAgentResponse(success=False, error="Stream ended without a result")

        except httpx.HTTPStatusError as e:
            body = e.response.text[:500]
            logger.error(
                "[invoke_stream] HTTP %d from agent-runtime for actor=%s: %s",
                e.response.status_code, request.actor_id, body,
            )
            return InvokeAgentResponse(
                success=False,
                error=f"Agent streaming HTTP {e.response.status_code}: {body[:200]}",
            )
        except Exception as e:
            logger.error(
                "[invoke_stream] Exception for actor=%s: %s",
                request.actor_id, e, exc_info=True,
            )
            return InvokeAgentResponse(
                success=False,
                error=f"Agent streaming error: {e}",
            )

    async def health_check(self) -> bool:
        """Check if the agent runtime service is healthy."""
        try:
            response = await self.http_client.get(
                f"{self.base_url}/health",
                timeout=5.0,
            )
            return response.status_code == 200
        except Exception:
            return False


class GameEngineClient:
    """HTTP client for game-engine service."""

    def __init__(self, base_url: str, http_client: httpx.AsyncClient) -> None:
        self.base_url = base_url.rstrip("/")
        self.http_client = http_client

    async def validate_action(self, request: ValidateActionRequest) -> ValidateActionResponse:
        """Validate an action against game rules."""
        try:
            payload = {
                "action": request.action.model_dump(mode="json"),
                "actor_id": request.actor_id,
                "state": request.state.model_dump(mode="json"),
            }

            response = await self.http_client.post(
                f"{self.base_url}/validate",
                json=payload,
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

            return ValidateActionResponse(
                valid=data.get("valid", False),
                errors=data.get("errors", []),
                warnings=data.get("warnings", []),
            )
        except httpx.HTTPStatusError as e:
            body = e.response.text[:500]
            logger.error("[validate_action] HTTP %d from game-engine: %s", e.response.status_code, body)
            return ValidateActionResponse(
                valid=False,
                errors=[f"Game engine returned HTTP {e.response.status_code}"],
            )
        except Exception as e:
            return ValidateActionResponse(
                valid=False,
                errors=[f"Game engine error: {str(e)}"],
            )

    async def resolve_action(self, request: ResolveActionRequest) -> ResolveActionResponse:
        """Resolve an action and get state patches."""
        try:
            payload = {
                "action": request.action.model_dump(mode="json"),
                "actor_id": request.actor_id,
                "state": request.state.model_dump(mode="json"),
            }
            if request.seed is not None:
                payload["seed"] = request.seed

            response = await self.http_client.post(
                f"{self.base_url}/resolve",
                json=payload,
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

            dice_rolls = [
                DiceRoll(
                    die=roll["die"],
                    value=roll["value"],
                    modifier=roll["modifier"],
                    total=roll["total"],
                )
                for roll in data.get("dice_rolls", [])
            ]

            state_patches = [
                StatePatch(
                    patch_type=patch["patch_type"],
                    target_id=patch["target_id"],
                    field=patch["field"],
                    old_value=patch["old_value"],
                    new_value=patch["new_value"],
                )
                for patch in data.get("state_patches", [])
            ]

            return ResolveActionResponse(
                success=data.get("success", False),
                action_type=ActionType(data.get("action_type", "defend")),
                description=data.get("description", ""),
                dice_rolls=dice_rolls,
                state_patches=state_patches,
                hit=data.get("hit"),
                damage=data.get("damage"),
            )
        except httpx.HTTPStatusError as e:
            body = e.response.text[:500]
            logger.error("[resolve_action] HTTP %d from game-engine: %s", e.response.status_code, body)
            return ResolveActionResponse(
                success=False,
                action_type=request.action.type if hasattr(request.action, "type") else ActionType.DEFEND,
                description="The action could not be resolved due to a rules error.",
            )
        except Exception as e:
            logger.error("[resolve_action] Error: %s", e, exc_info=True)
            return ResolveActionResponse(
                success=False,
                action_type=ActionType.DEFEND,
                description="The action could not be resolved.",
            )

    async def health_check(self) -> bool:
        """Check if the game engine service is healthy."""
        try:
            response = await self.http_client.get(
                f"{self.base_url}/health",
                timeout=5.0,
            )
            return response.status_code == 200
        except Exception:
            return False


class CommunicationServiceClient:
    """HTTP client for communication service."""

    def __init__(self, base_url: str, http_client: httpx.AsyncClient) -> None:
        self.base_url = base_url.rstrip("/")
        self.http_client = http_client

    async def create_message(self, request: CreateMessageRequest) -> CreateMessageResponse:
        """Create a new message."""
        try:
            payload = {
                "session_id": request.session_id,
                "scene_id": request.scene_id,
                "turn_number": request.turn_number,
                "phase": request.phase.value,
                "channel": request.channel.value,
                "sender_id": request.sender_id,
                "text": request.text,
                "recipient_ids": request.recipient_ids,
            }

            response = await self.http_client.post(
                f"{self.base_url}/messages",
                json=payload,
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()

            message = None
            if data.get("message"):
                message = TableMessage.model_validate(data["message"])

            return CreateMessageResponse(
                success=data.get("success", False),
                message=message,
                error=data.get("error"),
            )
        except httpx.HTTPStatusError as e:
            return CreateMessageResponse(
                success=False,
                error=f"HTTP error {e.response.status_code}: {e.response.text}",
            )
        except Exception as e:
            return CreateMessageResponse(
                success=False,
                error=f"Communication service error: {str(e)}",
            )

    async def register_session(self, session_id: str, state: GameState) -> bool:
        """Register a session with the communication service."""
        try:
            response = await self.http_client.post(
                f"{self.base_url}/sessions/{session_id}/register",
                json={"state": state.model_dump(mode="json")},
                timeout=10.0,
            )
            return response.status_code in (200, 201)
        except Exception:
            return False

    async def get_messages(
        self,
        session_id: str,
        viewer_id: str | None = None,
        turn_number: int | None = None,
    ) -> list[TableMessage]:
        """Get messages for a session."""
        try:
            params = {}
            if viewer_id:
                params["viewer_id"] = viewer_id
            if turn_number is not None:
                params["turn_number"] = turn_number

            response = await self.http_client.get(
                f"{self.base_url}/sessions/{session_id}/messages",
                params=params,
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()

            return [TableMessage.model_validate(m) for m in data.get("messages", [])]
        except Exception:
            return []

    async def health_check(self) -> bool:
        """Check if the communication service is healthy."""
        try:
            response = await self.http_client.get(
                f"{self.base_url}/health",
                timeout=5.0,
            )
            return response.status_code == 200
        except Exception:
            return False


@dataclass
class ServiceClients:
    """Container for all downstream service clients."""

    agent_runtime: AgentRuntimeClient
    game_engine: GameEngineClient
    communication: CommunicationServiceClient
    http_client: httpx.AsyncClient

    @classmethod
    def create(
        cls,
        agent_runtime_url: str,
        game_engine_url: str,
        communication_url: str,
    ) -> "ServiceClients":
        """Create service clients with a shared HTTP client."""
        http_client = httpx.AsyncClient()
        return cls(
            agent_runtime=AgentRuntimeClient(agent_runtime_url, http_client),
            game_engine=GameEngineClient(game_engine_url, http_client),
            communication=CommunicationServiceClient(communication_url, http_client),
            http_client=http_client,
        )

    async def close(self) -> None:
        """Close the shared HTTP client."""
        await self.http_client.aclose()

    async def check_all_health(self) -> dict[str, bool]:
        """Check health of all downstream services."""
        return {
            "agent_runtime": await self.agent_runtime.health_check(),
            "game_engine": await self.game_engine.health_check(),
            "communication": await self.communication.health_check(),
        }


def _coerce_position(value: object) -> Position | None:
    """Convert a position patch value into a proper Position object."""
    if value is None:
        return None
    if isinstance(value, Position):
        return value
    if isinstance(value, str):
        # Try to parse 'x,y' coordinate string
        parts = value.split(",")
        if len(parts) == 2:
            try:
                return Position(x=int(parts[0].strip()), y=int(parts[1].strip()), node_id=value)
            except ValueError:
                pass
        return Position(x=0, y=0, node_id=value)
    if isinstance(value, dict):
        return Position.model_validate(value)
    return Position(x=0, y=0, node_id=str(value))


def _parse_tile_target(target_id: str) -> tuple[int, int] | None:
    """Parse a tile target like 'tile:5,7' into (x, y) coordinates."""
    if not target_id.startswith("tile:"):
        return None
    coords = target_id[5:]  # Remove "tile:" prefix
    try:
        parts = coords.split(",")
        if len(parts) == 2:
            return int(parts[0].strip()), int(parts[1].strip())
    except (ValueError, AttributeError):
        pass
    return None


def apply_state_patches(state: GameState, patches: list[StatePatch]) -> GameState:
    """Apply resolution state patches to the game state."""
    characters = dict(state.characters)
    npcs = dict(state.npcs)
    flags = dict(state.flags)
    dungeon_map = state.dungeon_map

    for patch in patches:
        target_id = patch.target_id
        value = patch.new_value

        if patch.field == "position":
            value = _coerce_position(value)

        if target_id == "flags":
            flags[patch.field] = value

        elif target_id.startswith("tile:"):
            # Handle tile patches (e.g., door open/close)
            coords = _parse_tile_target(target_id)
            if coords and dungeon_map is not None:
                x, y = coords
                if 0 <= x < dungeon_map.width and 0 <= y < dungeon_map.height:
                    tile = dungeon_map.tiles[y][x]
                    if patch.field == "door_open":
                        dungeon_map.tiles[y][x] = tile.model_copy(update={"door_open": value})
                    else:
                        logger.warning("[apply_patch] Unknown field %r for tile %s", patch.field, target_id)

        elif target_id in characters:
            char = characters[target_id]
            if patch.field in ("hp", "alive", "status_effects", "position", "inventory"):
                characters[target_id] = char.model_copy(update={patch.field: value})
            else:
                logger.warning("[apply_patch] Unknown field %r for character %s", patch.field, target_id)

        elif target_id in npcs:
            npc = npcs[target_id]
            if patch.field in ("hp", "alive", "status_effects", "position", "inventory"):
                npcs[target_id] = npc.model_copy(update={patch.field: value})
            else:
                logger.warning("[apply_patch] Unknown field %r for npc %s", patch.field, target_id)

    return state.model_copy(update={"characters": characters, "npcs": npcs, "flags": flags, "dungeon_map": dungeon_map})


def get_visible_npcs_for_players(state: GameState) -> list:
    """Get NPCs that are currently visible to any player character via line of sight.
    
    This filters out NPCs that are hidden in fog of war or behind walls.
    Used to prevent the DM from narrating about enemies players haven't seen yet.
    """
    from shared_schemas.state import NpcState
    
    if state.dungeon_map is None:
        # No map means no fog of war, all NPCs visible
        return list(state.npcs.values())
    
    # Collect player positions
    player_positions: list[tuple[int, int]] = []
    for char in state.characters.values():
        if char.position:
            player_positions.append((char.position.x, char.position.y))
    
    if not player_positions:
        return []
    
    # Simple line-of-sight check using Bresenham's algorithm
    def has_los(px: int, py: int, tx: int, ty: int) -> bool:
        """Check if there's line of sight from player to target."""
        # Same position always has LOS
        if px == tx and py == ty:
            return True
        
        # Bresenham's line algorithm
        dx = abs(tx - px)
        dy = abs(ty - py)
        x, y = px, py
        sx = 1 if px < tx else -1
        sy = 1 if py < ty else -1
        
        if dx > dy:
            err = dx / 2
            while x != tx:
                x += sx
                err -= dy
                if err < 0:
                    y += sy
                    err += dx
                # Check if this intermediate point is a wall (skip start and end)
                if x != tx or y != ty:
                    if 0 <= x < state.dungeon_map.width and 0 <= y < state.dungeon_map.height:
                        if state.dungeon_map.tiles[y][x].terrain == "wall":
                            return False
        else:
            err = dy / 2
            while y != ty:
                y += sy
                err -= dx
                if err < 0:
                    x += sx
                    err += dy
                # Check if this intermediate point is a wall (skip start and end)
                if x != tx or y != ty:
                    if 0 <= x < state.dungeon_map.width and 0 <= y < state.dungeon_map.height:
                        if state.dungeon_map.tiles[y][x].terrain == "wall":
                            return False
        return True
    
    # Check each NPC for visibility
    visible_npcs: list[NpcState] = []
    for npc in state.npcs.values():
        if not npc.position:
            continue
        
        # Check if any player has LOS to this NPC
        for px, py in player_positions:
            # Simple range check (60 feet = 12 squares)
            dx = npc.position.x - px
            dy = npc.position.y - py
            if dx * dx + dy * dy > 144:  # 12^2 = 144
                continue
            
            if has_los(px, py, npc.position.x, npc.position.y):
                visible_npcs.append(npc)
                break  # Don't need to check other players
    
    return visible_npcs
