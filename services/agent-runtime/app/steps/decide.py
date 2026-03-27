"""Decide step: Action selection.

Given the accumulated perception, tool results, and any reflection feedback,
the model chooses a concrete action and produces a PlayerTurn JSON.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from ..adapters.base import ModelRequest
from ..pipeline import PipelineContext, RecentAction
from ..validation import OutputValidator


def _get_valid_adjacent_moves(ctx: PipelineContext) -> str:
    """Get list of valid adjacent tiles the actor can move to from current position."""
    if ctx.state.dungeon_map is None:
        return ""
    
    dungeon_map = ctx.state.dungeon_map
    actor = ctx.state.characters.get(ctx.actor_id)
    if not actor or not actor.position:
        return ""
    
    ax, ay = actor.position.x, actor.position.y
    
    valid_moves: list[str] = []
    doors: list[tuple[int, int]] = []
    
    for dx in [-1, 0, 1]:
        for dy in [-1, 0, 1]:
            if dx == 0 and dy == 0:
                continue
            nx, ny = ax + dx, ay + dy
            
            # Check bounds
            if not (0 <= nx < dungeon_map.width and 0 <= ny < dungeon_map.height):
                continue
            
            tile = dungeon_map.tiles[ny][nx]
            if not tile.revealed:
                continue
            
            terrain = tile.terrain.value if hasattr(tile.terrain, 'value') else str(tile.terrain)
            
            if terrain == "floor" or terrain == "difficult":
                valid_moves.append(f'"{nx},{ny}"')
            elif terrain in ("door", "door_locked"):
                if tile.door_open:
                    # Open door = walkable, treat like floor
                    valid_moves.append(f'"{nx},{ny}"')
                else:
                    # Closed door = need to open first
                    doors.append((nx, ny))
    
    result_parts = []
    result_parts.append(f"YOUR POSITION: ({ax},{ay})")
    
    if valid_moves:
        # Show ready-to-use move commands
        result_parts.append(f"VALID 1-STEP MOVES (copy exactly):")
        for mv in valid_moves[:4]:  # Limit to 4 examples
            result_parts.append(f'  {{"type": "move", "movement_path": [{mv}]}}')
    
    if doors:
        # Show how to open nearby doors (format must be "door:x,y")
        result_parts.append(f"CLOSED DOORS nearby - must open before walking through:")
        for dx, dy in doors[:2]:
            result_parts.append(f'  {{"type": "interact", "target_id": "door:{dx},{dy}", "interaction_type": "open"}}')
    
    if not valid_moves and not doors:
        result_parts.append("WARNING: No valid adjacent moves found. Use 'defend' to stay in place.")
    
    return "\n".join(result_parts)


def _generate_valid_path(
    ctx: PipelineContext,
    start_x: int,
    start_y: int,
    target_x: int,
    target_y: int,
    max_steps: int = 8,
    stop_adjacent: bool = False,
) -> list[str]:
    """Generate a valid step-by-step path from start to target.
    
    Uses simple greedy pathfinding - moves toward target avoiding walls.
    Returns list of coordinate strings like ["4,5", "4,6", "5,6"].
    """
    if ctx.state.dungeon_map is None:
        return []
    
    dungeon_map = ctx.state.dungeon_map
    path: list[str] = []
    cx, cy = start_x, start_y
    
    for _ in range(max_steps):
        # Check if we've reached target (or adjacent if stop_adjacent)
        dist = max(abs(target_x - cx), abs(target_y - cy))
        if dist == 0 or (stop_adjacent and dist <= 1):
            break
        
        # Find best adjacent tile to move to
        best_next = None
        best_dist = float('inf')
        
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx == 0 and dy == 0:
                    continue
                nx, ny = cx + dx, cy + dy
                
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
                # Skip CLOSED doors for pathfinding (would need interact first)
                # But OPEN doors are walkable!
                if terrain in ("door", "door_locked") and not tile.door_open:
                    continue
                
                # Calculate distance to target
                new_dist = max(abs(target_x - nx), abs(target_y - ny))
                if new_dist < best_dist:
                    best_dist = new_dist
                    best_next = (nx, ny)
        
        if best_next is None:
            break  # No valid move found
        
        cx, cy = best_next
        path.append(f"{cx},{cy}")
    
    return path


def _analyze_action_history(recent_actions: list[RecentAction]) -> str:
    """Analyze recent actions and return guidance to avoid repetitive behavior."""
    if not recent_actions:
        return ""

    # Count action types and targets
    action_counts: Counter[str] = Counter()
    target_counts: Counter[str] = Counter()
    inspect_targets: list[str] = []
    defend_count = 0

    for action in recent_actions:
        action_counts[action.action_type] += 1
        if action.target_id:
            target_counts[action.target_id] += 1
        if action.action_type == "inspect" and action.target_id:
            inspect_targets.append(action.target_id)
        if action.action_type == "defend":
            defend_count += 1

    warnings: list[str] = []

    # Warn about repeated inspections of the same target
    for target, count in target_counts.items():
        if count >= 2 and target in inspect_targets:
            warnings.append(
                f"WARNING: You have already inspected '{target}' {count} times. "
                f"If you found something interesting, use 'interact' to pick it up or 'move' to explore elsewhere."
            )

    # Warn about excessive defending
    if defend_count >= 2:
        warnings.append(
            f"WARNING: You have defended {defend_count} times recently. "
            f"Consider taking offensive action, moving to explore, or interacting with objects."
        )

    # Warn about lack of movement
    move_actions = action_counts.get("move", 0) + action_counts.get("move_and_attack", 0)
    if len(recent_actions) >= 3 and move_actions == 0:
        warnings.append(
            "WARNING: You haven't moved in several turns. "
            "Consider exploring new areas of the map or approaching enemies."
        )

    if warnings:
        return "\n\nACTION HISTORY ANALYSIS:\n" + "\n".join(warnings)
    return ""


def _get_exploration_hints(ctx: PipelineContext) -> str:
    """Generate hints about unexplored areas and discoverable content."""
    hints: list[str] = []

    # Check for discovered but not-yet-collected items
    if ctx.state.flags:
        # Filter out system flags
        system_flags = {
            "story_seed", "story_genre", "story_themes", "story_difficulty",
            "story_random_seed", "map_complexity", "generate_dynamic_map",
            "difficulty", "random_seed",
        }
        discovered_secrets = [
            k for k, v in ctx.state.flags.items()
            if v and k not in system_flags and not k.startswith("story_")
            and ("found" in k or "revealed" in k or "discovered" in k)
        ]
        if discovered_secrets:
            hints.append(
                f"DISCOVERED SECRETS: {', '.join(discovered_secrets)}. "
                f"Use 'interact' action to pick up items or activate mechanisms."
            )

    # Check for frontier tiles (revealed tiles adjacent to unrevealed areas)
    # These are good destinations for exploration
    if ctx.state.dungeon_map:
        dungeon_map = ctx.state.dungeon_map
        actor_pos = None
        actor = ctx.state.characters.get(ctx.actor_id)
        if actor and actor.position:
            actor_pos = (actor.position.x, actor.position.y)

        # Find frontier tiles: revealed floor tiles that border unrevealed tiles
        frontier_tiles: list[tuple[int, int, int]] = []  # (x, y, distance)
        
        if actor_pos:
            ax, ay = actor_pos
            
            for y in range(dungeon_map.height):
                for x in range(dungeon_map.width):
                    tile = dungeon_map.tiles[y][x]
                    # Only consider revealed walkable tiles
                    if not tile.revealed or tile.terrain.value in ("wall", "pit", "water_deep"):
                        continue
                    
                    # Check if this tile borders any unrevealed tile
                    borders_unknown = False
                    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < dungeon_map.width and 0 <= ny < dungeon_map.height:
                            neighbor = dungeon_map.tiles[ny][nx]
                            if not neighbor.revealed:
                                borders_unknown = True
                                break
                    
                    if borders_unknown:
                        dist = abs(x - ax) + abs(y - ay)  # Manhattan distance
                        frontier_tiles.append((x, y, dist))
            
            # Sort by distance
            frontier_tiles.sort(key=lambda t: t[2])
            
            if frontier_tiles:
                nearest = frontier_tiles[:3]
                coords = [f"({t[0]},{t[1]})" for t in nearest]
                hints.append(
                    f"FRONTIER TILES (edge of explored area): {', '.join(coords)}. "
                    f"Move to these tiles to reveal more of the dungeon."
                )
                
                # Generate example path to nearest frontier tile
                fx, fy, _ = frontier_tiles[0]
                example_path = _generate_valid_path(ctx, ax, ay, fx, fy, max_steps=6)
                if example_path:
                    path_str = ', '.join(f'"{p}"' for p in example_path)
                    hints.append(
                        f"EXAMPLE MOVE to ({fx},{fy}): "
                        f"{{\"type\": \"move\", \"movement_path\": [{path_str}]}}"
                    )
        
        # Check for open doors that lead to unexplored areas - walk through them!
        if dungeon_map:
            open_doors_to_explore: list[tuple[int, int, int]] = []
            for y in range(dungeon_map.height):
                for x in range(dungeon_map.width):
                    tile = dungeon_map.tiles[y][x]
                    if tile.revealed and tile.terrain.value in ("door", "door_locked") and tile.door_open:
                        # Check if any adjacent tile is unexplored
                        has_unexplored_neighbor = False
                        for ddx, ddy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                            nx, ny = x + ddx, y + ddy
                            if 0 <= nx < dungeon_map.width and 0 <= ny < dungeon_map.height:
                                if not dungeon_map.tiles[ny][nx].revealed:
                                    has_unexplored_neighbor = True
                                    break
                        if has_unexplored_neighbor:
                            dist = max(abs(x - ax), abs(y - ay))
                            open_doors_to_explore.append((x, y, dist))
            
            open_doors_to_explore.sort(key=lambda t: t[2])
            
            if open_doors_to_explore:
                dx, dy, dist = open_doors_to_explore[0]
                # Generate path THROUGH the open door
                path_through = _generate_valid_path(ctx, ax, ay, dx, dy, max_steps=8, stop_adjacent=False)
                if path_through:
                    path_str = ', '.join(f'"{p}"' for p in path_through)
                    hints.append(
                        f"OPEN DOOR at ({dx},{dy}) leads to UNEXPLORED area! Walk through it:\n"
                        f"  {{\"type\": \"move\", \"movement_path\": [{path_str}]}}"
                    )
        
        # Check for visible closed doors that block progress
        if dungeon_map:
            closed_doors: list[tuple[int, int, int]] = []
            for y in range(dungeon_map.height):
                for x in range(dungeon_map.width):
                    tile = dungeon_map.tiles[y][x]
                    if tile.revealed and tile.terrain.value in ("door", "door_locked") and not tile.door_open:
                        dist = max(abs(x - ax), abs(y - ay))  # Chebyshev distance
                        closed_doors.append((x, y, dist))
            
            closed_doors.sort(key=lambda t: t[2])
            
            if closed_doors:
                dx, dy, dist = closed_doors[0]
                if dist <= 1:
                    # Adjacent to door - suggest opening it
                    hints.append(
                        f"CLOSED DOOR at ({dx},{dy}) is ADJACENT to you!\n"
                        f"Open it now: {{\"type\": \"interact\", \"target_id\": \"door:{dx},{dy}\", \"interaction_type\": \"open\"}}"
                    )
                else:
                    # Need to move to door first
                    path_to_door = _generate_valid_path(ctx, ax, ay, dx, dy, max_steps=8, stop_adjacent=True)
                    if path_to_door:
                        path_str = ', '.join(f'"{p}"' for p in path_to_door)
                        hints.append(
                            f"CLOSED DOOR at ({dx},{dy}) blocks exploration. Move adjacent first:\n"
                            f"  {{\"type\": \"move\", \"movement_path\": [{path_str}]}}\n"
                            f"Then open it next turn with: {{\"type\": \"interact\", \"target_id\": \"door:{dx},{dy}\", \"interaction_type\": \"open\"}}"
                        )
        
        # Check for visible NPCs to give tactical context
        visible_npcs = ctx.agent_context.visible_state.npcs
        hostile_count = sum(1 for npc in visible_npcs.values() if npc.disposition == "hostile" and npc.alive)
        
        if hostile_count == 0 and frontier_tiles:
            hints.append(
                "NO ENEMIES VISIBLE. Focus on exploration - move toward frontier tiles "
                "to reveal more of the map and locate objectives."
            )

    if hints:
        return "\n\nEXPLORATION OPPORTUNITIES:\n" + "\n".join(hints)
    return ""


class DecideStep:
    """Asks the model to choose and output a structured PlayerTurn action."""

    def __init__(self, validator: OutputValidator | None = None) -> None:
        self._validator = validator or OutputValidator()

    @property
    def name(self) -> str:
        return "decide"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        context_parts: list[str] = []

        if ctx.perception:
            context_parts.append(f"Your tactical assessment:\n{ctx.perception}")

        if ctx.tool_results:
            context_parts.append("Information gathered:")
            for tool_name, result in ctx.tool_results.items():
                context_parts.append(f"  [{tool_name}]: {result[:300]}")

        if ctx.reflection_feedback:
            context_parts.append(f"\nPrevious attempt feedback:\n{ctx.reflection_feedback}")
            context_parts.append("Take this feedback into account and choose a better action.")

        if ctx.state.objectives:
            context_parts.append("Active objectives:")
            for obj in ctx.state.objectives:
                context_parts.append(f"  [{obj.status}] {obj.label}: {obj.summary}")

        if ctx.state.flags:
            # Filter out meta/system flags that aren't actual game objects
            # These are configuration flags, not things players can interact with
            system_flags = {
                "story_seed", "story_genre", "story_themes", "story_difficulty",
                "story_random_seed", "map_complexity", "generate_dynamic_map",
                "difficulty", "random_seed",
            }
            incomplete_flags = [
                k for k, v in ctx.state.flags.items() 
                if not v and k not in system_flags and not k.startswith("story_")
            ]
            if incomplete_flags:
                context_parts.append(f"Unexplored areas/objects: {', '.join(incomplete_flags)}")

        # Add action history analysis to prevent repetitive loops
        action_history_warning = _analyze_action_history(ctx.recent_actions)
        if action_history_warning:
            context_parts.append(action_history_warning)

        # Add exploration hints
        exploration_hints = _get_exploration_hints(ctx)
        if exploration_hints:
            context_parts.append(exploration_hints)

        # Add valid adjacent moves - crucial for pathfinding
        valid_moves = _get_valid_adjacent_moves(ctx)
        if valid_moves:
            context_parts.append(f"MOVEMENT OPTIONS:\n{valid_moves}")

        context_block = "\n\n".join(context_parts) if context_parts else ""

        prompt = f"""{context_block}

Now choose your action. You must respond with a valid JSON object:
{{
  "thought": "Your private tactical reasoning",
  "speech": "What you say aloud in character (optional)",
  "table_talk": "Tactical coordination with allies (optional)",
  "action": {{
    "type": "<one of: {', '.join(str(a) for a in ctx.allowed_actions)}>",
    ... action-specific fields ...
  }}
}}

Action field requirements:
- attack: {{"type": "attack", "target_id": "<entity_id>"}}
- move: {{"type": "move", "movement_path": ["<pos1>", "<pos2>"]}}
- move_and_attack: {{"type": "move_and_attack", "movement_path": ["<pos>"], "target_id": "<entity_id>"}}
- defend: {{"type": "defend", "stance": "guard|dodge|brace"}}
- inspect: {{"type": "inspect", "target_id": "<object_name_or_location>"}} (e.g. "altar", "altar-platform")
- interact: {{"type": "interact", "target_id": "<object_id>", "interaction_type": "pickup|use|open|pull"}}
- cast_spell_basic: {{"type": "cast_spell_basic", "spell_id": "<spell_id>", "target_id": "<entity_id>"}}

IMPORTANT RULES:
- Avoid repeating the same action multiple times. If you've inspected something, either interact with it or move on.
- USE FULL MOVEMENT: If EXPLORATION OPPORTUNITIES shows a move command, COPY IT EXACTLY - it uses your full movement budget!
- Don't move just 1 tile when you can move 6-8 tiles toward your destination.

At least one of speech, table_talk, or action is required."""

        if ctx.messages_history:
            messages: list[dict[str, Any]] = list(ctx.messages_history)
            messages.append({"role": "user", "content": prompt})
            request = ModelRequest(
                system_prompt=ctx.system_prompt,
                user_prompt="",
                messages=messages,
                temperature=ctx.temperature,
                max_tokens=4096,
                response_format={"type": "json_object"},
            )
        else:
            request = ModelRequest(
                system_prompt=ctx.system_prompt,
                user_prompt=f"{ctx.user_prompt}\n\n{prompt}",
                temperature=ctx.temperature,
                max_tokens=4096,
                response_format={"type": "json_object"},
            )

        response = await ctx.adapter.generate(request)

        step_trace = ctx.trace.steps[-1] if ctx.trace.steps else None
        if step_trace and step_trace.step_name == self.name:
            step_trace.model_calls += 1
            step_trace.tokens_used += response.tokens_used

        if not response.success:
            return ctx

        result = self._validator.validate_player_turn(response.raw_text)
        if result.valid and result.parsed:
            ctx.proposed_turn = result.parsed
        else:
            ctx.extra["decide_raw_text"] = response.raw_text
            ctx.extra["decide_errors"] = result.errors

        return ctx
