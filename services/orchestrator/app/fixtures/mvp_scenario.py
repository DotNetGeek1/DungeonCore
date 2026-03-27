"""MVP scenario: The Goblin Ambush - a dungeon corridor with combat and puzzle elements."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from shared_schemas.enums import ActorRole, ScenePhase, Visibility
from shared_schemas.state import (
    CharacterState,
    DungeonMap,
    GameState,
    MapTile,
    NpcState,
    ObjectiveState,
    Position,
    SceneState,
    TerrainType,
    TileContent,
    TurnState,
    VisibilityScope,
)


class StoryGenre(str, Enum):
    CLASSIC_FANTASY = "classic_fantasy"
    DARK_FANTASY = "dark_fantasy"
    HORROR = "horror"
    MYSTERY = "mystery"
    HEROIC = "heroic"
    SURVIVAL = "survival"


class DifficultyLevel(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    DEADLY = "deadly"


class MapComplexity(str, Enum):
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


@dataclass
class StoryConfig:
    """Configuration for procedurally generating a unique adventure."""
    genre: StoryGenre = StoryGenre.CLASSIC_FANTASY
    themes: list[str] = field(default_factory=lambda: ["exploration", "combat"])
    difficulty: DifficultyLevel = DifficultyLevel.MEDIUM
    seed: int | None = None
    map_complexity: MapComplexity = MapComplexity.MEDIUM
    story_seed: str | None = None
    num_rooms: int = 5
    enemy_density: float = 0.5
    treasure_density: float = 0.3
    trap_density: float = 0.2
    custom_hooks: list[str] = field(default_factory=list)

    def get_seed(self) -> int:
        """Get the seed, generating one if not set."""
        if self.seed is None:
            self.seed = random.randint(1, 2**31 - 1)
        return self.seed


STORY_PRESETS: dict[str, StoryConfig] = {
    "classic_dungeon": StoryConfig(
        genre=StoryGenre.CLASSIC_FANTASY,
        themes=["exploration", "combat", "treasure"],
        difficulty=DifficultyLevel.MEDIUM,
        map_complexity=MapComplexity.MEDIUM,
        story_seed="A forgotten dungeon awaits brave adventurers",
    ),
    "haunted_crypt": StoryConfig(
        genre=StoryGenre.HORROR,
        themes=["undead", "mystery", "ancient evil"],
        difficulty=DifficultyLevel.HARD,
        map_complexity=MapComplexity.COMPLEX,
        story_seed="The dead do not rest easy in these halls",
        enemy_density=0.7,
        trap_density=0.4,
    ),
    "goblin_warren": StoryConfig(
        genre=StoryGenre.CLASSIC_FANTASY,
        themes=["combat", "ambush", "tribal"],
        difficulty=DifficultyLevel.EASY,
        map_complexity=MapComplexity.SIMPLE,
        story_seed="Goblins have been raiding nearby villages",
        num_rooms=3,
    ),
    "dark_temple": StoryConfig(
        genre=StoryGenre.DARK_FANTASY,
        themes=["cultists", "ritual", "forbidden knowledge"],
        difficulty=DifficultyLevel.HARD,
        map_complexity=MapComplexity.COMPLEX,
        story_seed="A cult performs dark rituals in the depths",
        trap_density=0.5,
    ),
    "survival_escape": StoryConfig(
        genre=StoryGenre.SURVIVAL,
        themes=["escape", "resources", "time pressure"],
        difficulty=DifficultyLevel.DEADLY,
        map_complexity=MapComplexity.MEDIUM,
        story_seed="You must escape before the dungeon collapses",
        enemy_density=0.8,
    ),
}


def get_story_preset(name: str) -> StoryConfig:
    """Get a story preset by name, or default to classic_dungeon."""
    return STORY_PRESETS.get(name, STORY_PRESETS["classic_dungeon"])


@dataclass
class SceneConfig:
    scene_id: str
    scene_name: str
    scene_summary: str
    location_name: str
    max_discussion_messages: int = 3
    story_config: StoryConfig | None = None


MVP_SCENE_CONFIG = SceneConfig(
    scene_id="scene-goblin-ambush",
    scene_name="The Goblin Ambush",
    scene_summary=(
        "A dimly lit dungeon corridor stretches before you. Flickering torchlight "
        "casts dancing shadows on moss-covered stone walls. At the far end, an ancient "
        "altar covered in strange runes catches your eye. The air is thick with tension - "
        "you sense movement in the darkness ahead. Three goblins emerge from the shadows, "
        "led by a robed figure clutching a gnarled staff - a goblin shaman."
    ),
    location_name="Dungeon Corridor - East Wing",
    max_discussion_messages=3,
    story_config=StoryConfig(
        genre=StoryGenre.CLASSIC_FANTASY,
        themes=["combat", "mystery", "ancient artifacts"],
        difficulty=DifficultyLevel.MEDIUM,
        story_seed="Goblins have taken residence in ancient ruins, drawn by dark magic",
    ),
)


def _make_floor() -> MapTile:
    return MapTile(terrain=TerrainType.FLOOR, content=TileContent.EMPTY, revealed=False)


def _make_wall() -> MapTile:
    return MapTile(terrain=TerrainType.WALL, content=TileContent.EMPTY, revealed=True)


def _make_tile(
    terrain: TerrainType = TerrainType.FLOOR,
    content: TileContent = TileContent.EMPTY,
    revealed: bool = False,
    label: str | None = None,
) -> MapTile:
    return MapTile(terrain=terrain, content=content, revealed=revealed, label=label)


def create_goblin_ambush_map() -> DungeonMap:
    """
    Create the Goblin Ambush dungeon map (25x12 grid).

    The map has two zones:
    1. The Main Corridor (cols 0-14, rows 0-11) - REVEALED at start
    2. The Eastern Chamber (cols 15-24, rows 0-11) - FOGGED (unexplored)

    Main Corridor layout (W=wall .=floor D=door T=torch ~=difficult P=pillar):
    Row  0:  WWWWWWWWWWWWWWW WWWWWWWWWW
    Row  1:  W.............W W........W
    Row  2:  WT............W W.B......W  (B=bookshelf)
    Row  3:  W.....~~......W W........W
    Row  4:  W..P..~~..P...W W........W
    Row  5:  W.............W W........W
    Row  6:  W..........D..WWWWWW.....W  (D=door connecting zones)
    Row  7:  W.............W W........W
    Row  8:  W.........A.$.W W....f...W  (A=altar $=treasure f=campfire)
    Row  9:  W.............W W........W
    Row 10:  W..............W W.......W
    Row 11:  WWWWWWWWWWWWWWW WWWWWWWWWW

    Actors: Players at (2,9)(2,10), Goblins at (5,5)(6,5), Shaman at (9,8)
    """
    W = 25
    H = 12

    rows: list[list[MapTile]] = []
    for y in range(H):
        row: list[MapTile] = []
        for x in range(W):
            # Outer border walls
            if y == 0 or y == H - 1:
                row.append(_make_wall())
            elif x == 0 or x == W - 1:
                row.append(_make_wall())
            # Dividing wall between the two zones (col 15), except door gap
            elif x == 15:
                row.append(_make_wall())
            else:
                row.append(_make_floor())
        rows.append(row)

    # ── Main Corridor (cols 1-14) ──────────────────────────────────────────
    # Left/right inner walls
    for y in range(1, H - 1):
        rows[y][14] = _make_wall()  # right wall of corridor (col 14 is wall)

    # Rubble/difficult terrain
    for y in range(3, 5):
        for x in range(6, 8):
            rows[y][x] = _make_tile(TerrainType.DIFFICULT, TileContent.RUBBLE)

    # Torches on the left wall
    rows[2][1] = _make_tile(TerrainType.FLOOR, TileContent.TORCH)
    rows[8][1] = _make_tile(TerrainType.FLOOR, TileContent.TORCH)

    # Pillars for cover
    rows[4][3] = _make_tile(TerrainType.FLOOR, TileContent.PILLAR)
    rows[4][11] = _make_tile(TerrainType.FLOOR, TileContent.PILLAR)

    # Altar platform and treasure
    rows[8][9] = _make_tile(TerrainType.FLOOR, TileContent.ALTAR, label="altar-platform")
    rows[8][11] = _make_tile(TerrainType.FLOOR, TileContent.TREASURE_CHEST, label="treasure-chest")

    # Door connecting to the eastern chamber (hole in dividing wall at col 15, row 6)
    rows[6][15] = _make_tile(TerrainType.DOOR, TileContent.EMPTY, label="east-door")

    # ── Eastern Chamber (cols 16-24) - starts FOGGED ──────────────────────
    # Inner walls for the chamber
    for y in range(1, H - 1):
        rows[y][16] = _make_floor()  # first col of chamber is floor

    # Bookshelf in the chamber
    rows[2][18] = _make_tile(TerrainType.FLOOR, TileContent.BOOKSHELF, revealed=False)

    # Campfire in the middle of the chamber
    rows[8][20] = _make_tile(TerrainType.FLOOR, TileContent.CAMPFIRE, revealed=False)

    # Statue
    rows[5][22] = _make_tile(TerrainType.FLOOR, TileContent.STATUE, revealed=False)

    # Hidden trap in the chamber
    rows[4][19] = _make_tile(TerrainType.FLOOR, TileContent.TRAP_HIDDEN, revealed=False)

    # ── Reveal main corridor, keep eastern chamber fogged ─────────────────
    for y in range(1, H - 1):
        for x in range(1, 15):  # Only reveal corridor (cols 1-14)
            tile = rows[y][x]
            rows[y][x] = MapTile(
                terrain=tile.terrain,
                content=tile.content,
                revealed=True,
                label=tile.label,
                elevation=tile.elevation,
            )
    # The door tile itself is visible (players can see the door from the corridor)
    rows[6][15] = MapTile(
        terrain=TerrainType.DOOR,
        content=TileContent.EMPTY,
        revealed=True,
        label="east-door",
    )
    # Eastern chamber (cols 16-24) stays fogged (revealed=False by default)

    return DungeonMap(
        name="Dungeon Corridor - East Wing",
        width=W,
        height=H,
        tiles=rows,
        default_terrain=TerrainType.FLOOR,
    )


def create_fighter_character(actor_id: str) -> CharacterState:
    """Fighter: STR-based melee with longsword + shield + chain_mail (AC 16)."""
    return CharacterState(
        actor_id=actor_id,
        name="Theron Ironblade",
        role=ActorRole.PLAYER,
        hp=28,
        max_hp=28,
        ac=16,
        initiative=2,
        position=Position(x=2, y=9, zone_id="dungeon-east"),
        status_effects=[],
        inventory=["longsword", "shield", "chain_mail", "handaxe"],
        spell_slots={},
        character_class="fighter",
        player_slot="player_1",
        visibility_scope=VisibilityScope(visibility=Visibility.PUBLIC),
    )


def create_rogue_character(actor_id: str) -> CharacterState:
    """Rogue: DEX-based with shortsword + dagger + leather armor (AC 14)."""
    return CharacterState(
        actor_id=actor_id,
        name="Lyra Shadowstep",
        role=ActorRole.PLAYER,
        hp=20,
        max_hp=20,
        ac=14,
        initiative=4,
        position=Position(x=2, y=10, zone_id="dungeon-east"),
        status_effects=[],
        inventory=["shortsword", "dagger", "leather"],
        spell_slots={},
        character_class="rogue",
        player_slot="player_2",
        visibility_scope=VisibilityScope(visibility=Visibility.PUBLIC),
    )


def create_goblin(actor_id: str, name: str, pos_x: int, pos_y: int) -> NpcState:
    """Goblin: scimitar + shortbow, AC 12 (leather + shield equivalent)."""
    return NpcState(
        actor_id=actor_id,
        name=name,
        role=ActorRole.ENEMY,
        hp=7,
        max_hp=7,
        ac=12,
        initiative=1,
        position=Position(x=pos_x, y=pos_y, zone_id="dungeon-east"),
        status_effects=[],
        inventory=["scimitar", "shortbow"],
        spell_slots={},
        disposition="hostile",
        behavior_tag="melee_aggressive",
        visibility_scope=VisibilityScope(visibility=Visibility.PUBLIC),
    )


def create_goblin_shaman(actor_id: str) -> NpcState:
    """Goblin Shaman: quarterstaff + spells, AC 11."""
    return NpcState(
        actor_id=actor_id,
        name="Skrix the Shaman",
        role=ActorRole.ENEMY,
        hp=15,
        max_hp=15,
        ac=11,
        initiative=3,
        position=Position(x=9, y=8, zone_id="dungeon-east"),
        status_effects=[],
        inventory=["quarterstaff"],
        spell_slots={"1": 2, "2": 1},
        disposition="hostile",
        behavior_tag="caster_support",
        visibility_scope=VisibilityScope(visibility=Visibility.PUBLIC),
    )


def _generate_dynamic_scene_summary(story_config: StoryConfig) -> tuple[str, str, str]:
    """Generate a dynamic scene name, summary, and location based on story config."""
    genre = story_config.genre
    themes = story_config.themes

    scene_templates = {
        StoryGenre.CLASSIC_FANTASY: (
            "The Adventure Begins",
            "A new adventure awaits. The heroes stand ready to face whatever challenges lie ahead.",
            "A Starting Location",
        ),
        StoryGenre.DARK_FANTASY: (
            "Into the Shadows",
            "Darkness gathers. The heroes must navigate treacherous paths where hope flickers dimly.",
            "A Shadowed Place",
        ),
        StoryGenre.HORROR: (
            "Whispers in the Dark",
            "Something sinister stirs. The heroes feel eyes upon them from the surrounding darkness.",
            "A Foreboding Location",
        ),
        StoryGenre.MYSTERY: (
            "The First Clue",
            "A mystery unfolds. The heroes must piece together fragments of truth hidden in shadow.",
            "An Enigmatic Place",
        ),
        StoryGenre.HEROIC: (
            "The Call to Glory",
            "Destiny beckons! The heroes stand at the threshold of legend, ready to prove their worth.",
            "A Place of Significance",
        ),
        StoryGenre.SURVIVAL: (
            "Against the Odds",
            "Resources are scarce and danger lurks everywhere. Only the cunning will survive.",
            "A Harsh Environment",
        ),
    }

    name, summary, location = scene_templates.get(
        genre,
        ("The Adventure", "An adventure begins.", "Unknown Location"),
    )

    theme_additions = []
    if "exploration" in themes:
        theme_additions.append("Unknown territories await discovery.")
    if "combat" in themes:
        theme_additions.append("Enemies stand between the heroes and their goals.")
    if "mystery" in themes:
        theme_additions.append("Secrets lie hidden, waiting to be uncovered.")
    if "puzzle" in themes:
        theme_additions.append("Ancient mechanisms guard the way forward.")

    if theme_additions:
        summary = summary + " " + " ".join(theme_additions)

    return name, summary, location


def create_mvp_game_state(
    campaign_id: str,
    session_id: str,
    config: SceneConfig | None = None,
    story_config: StoryConfig | None = None,
    fighter_id: str | None = None,
    rogue_id: str | None = None,
) -> GameState:
    """Create the complete MVP game state for the Goblin Ambush scenario."""
    if config is None:
        config = MVP_SCENE_CONFIG

    # Use story config from scene config if not explicitly provided
    if story_config is None:
        story_config = config.story_config or StoryConfig()

    # Determine if this is a custom adventure (different story config than default)
    is_custom_adventure = story_config != config.story_config

    fighter_id = fighter_id or "player-fighter-001"
    rogue_id = rogue_id or "player-rogue-001"

    fighter = create_fighter_character(fighter_id)
    rogue = create_rogue_character(rogue_id)

    characters = {
        fighter_id: fighter,
        rogue_id: rogue,
    }

    # For custom adventures, start with no predefined enemies - let DM create them
    # For default MVP scenario, use the classic goblin ambush
    if is_custom_adventure:
        npcs = {}
        objectives = [
            ObjectiveState(
                objective_id="obj-explore",
                label="Explore the Area",
                status="active",
                summary="Discover what lies ahead and overcome any challenges.",
            ),
            ObjectiveState(
                objective_id="obj-survive",
                label="Survive",
                status="active",
                summary="Keep the party alive through whatever dangers await.",
            ),
        ]
    else:
        goblin_1 = create_goblin("npc-goblin-001", "Grimfang", 5, 8)
        goblin_2 = create_goblin("npc-goblin-002", "Snarl", 5, 9)
        shaman = create_goblin_shaman("npc-shaman-001")

        npcs = {
            goblin_1.actor_id: goblin_1,
            goblin_2.actor_id: goblin_2,
            shaman.actor_id: shaman,
        }

        objectives = [
            ObjectiveState(
                objective_id="obj-clear-corridor",
                label="Clear the Corridor",
                status="active",
                summary="Defeat the goblins blocking your path through the dungeon.",
            ),
            ObjectiveState(
                objective_id="obj-investigate-altar",
                label="Investigate the Altar",
                status="active",
                summary="The ancient altar may hold secrets. Examine it when safe.",
            ),
        ]

    # Store story configuration in flags for DM reference
    # Note: themes and custom_hooks are serialized as comma-separated strings
    # since flags only support primitive types (str, int, float, bool)
    if is_custom_adventure:
        # Clean flags for custom adventures - no goblin-specific state
        flags: dict[str, Any] = {
            "story_genre": story_config.genre.value,
            "story_themes": ",".join(story_config.themes),
            "story_difficulty": story_config.difficulty.value,
            "story_seed": story_config.story_seed or "",
            "story_random_seed": story_config.get_seed(),
            "map_complexity": story_config.map_complexity.value,
        }
    else:
        # Default MVP scenario flags
        flags = {
            "altar_examined": False,
            "hidden_compartment_found": False,
            "shaman_revealed_weakness": False,
            "corridor_cleared": False,
            "story_genre": story_config.genre.value,
            "story_themes": ",".join(story_config.themes),
            "story_difficulty": story_config.difficulty.value,
            "story_seed": story_config.story_seed or "",
            "story_random_seed": story_config.get_seed(),
            "map_complexity": story_config.map_complexity.value,
        }

    active_actor_id = rogue_id

    # For custom adventures, start with no map - DM will generate it
    # For default MVP, use the predefined goblin ambush map
    if is_custom_adventure:
        dungeon_map = None
    else:
        dungeon_map = create_goblin_ambush_map()

    # For custom adventures, use dynamic scene info; otherwise use default MVP config
    if is_custom_adventure:
        scene_name, scene_summary, location_name = _generate_dynamic_scene_summary(story_config)
        scene_id = f"scene-{story_config.genre.value}-{session_id[:8]}"
    else:
        scene_id = config.scene_id
        scene_name = config.scene_name
        scene_summary = config.scene_summary
        location_name = config.location_name

    return GameState(
        campaign_id=campaign_id,
        session_id=session_id,
        scene=SceneState(
            scene_id=scene_id,
            name=scene_name,
            summary=scene_summary,
            phase=ScenePhase.SCENE_INTRO,
            turn_number=1,
            active_actor_id=active_actor_id,
            location_name=location_name,
        ),
        turn=TurnState(
            turn_number=1,
            round_number=1,
            active_actor_id=active_actor_id,
            phase=ScenePhase.SCENE_INTRO,
            discussion_open=False,
            max_discussion_messages=config.max_discussion_messages,
            remaining_discussion_messages=config.max_discussion_messages,
        ),
        characters=characters,
        npcs=npcs,
        objectives=objectives,
        flags=flags,
        dungeon_map=dungeon_map,
    )


INSPECTABLE_OBJECTS = {
    "altar": {
        "object_id": "obj-ancient-altar",
        "name": "Ancient Altar",
        "location": "altar-platform",
        "description": (
            "A weathered stone altar covered in faded runes. Despite centuries of neglect, "
            "the symbols seem to pulse with a faint inner light. The craftsmanship suggests "
            "this predates the goblins' occupation by many ages."
        ),
        "inspect_dc": 12,
        "secrets": {
            "hidden_compartment": {
                "dc": 15,
                "description": (
                    "Your careful examination reveals a loose stone at the altar's base. "
                    "Behind it, a hidden compartment contains a dusty scroll and a small "
                    "vial of glowing liquid."
                ),
                "contents": ["scroll_of_protection", "potion_of_healing"],
            },
            "rune_meaning": {
                "dc": 18,
                "description": (
                    "The runes speak of an ancient binding ritual. Creatures of darkness "
                    "are weakened near this altar - the shaman's magic may be less potent here."
                ),
                "effect": "shaman_magic_weakened",
            },
        },
    },
}
