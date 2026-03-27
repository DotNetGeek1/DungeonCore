from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

from pydantic import TypeAdapter

from .models import (
    AbilityModifierEntry,
    ArmorEntry,
    ClassEntry,
    CombatAction,
    ConditionEntry,
    CoverEntry,
    DamageType,
    ExhaustionLevel,
    FeatEntry,
    GearEntry,
    MountEntry,
    MovementRule,
    MulticlassRequirement,
    ProficiencyBonusEntry,
    RaceEntry,
    SkillEntry,
    SpellcastingRule,
    SpellEntry,
    ToolEntry,
    WeaponEntry,
)

T = TypeVar("T")

DATA_DIR = Path(__file__).parent / "data"


def _load_json(path: Path) -> list[dict] | dict:  # type: ignore[type-arg]
    with open(path, encoding="utf-8") as f:
        return json.load(f)  # type: ignore[no-any-return]


def _load_list(path: Path, model: type[T]) -> list[T]:
    raw = _load_json(path)
    if not isinstance(raw, list):
        raw = raw.get("entries", raw.get("items", [raw]))
    adapter: TypeAdapter[list[T]] = TypeAdapter(list[model])
    return adapter.validate_python(raw)


def _load_dict(path: Path, model: type[T], key_field: str) -> dict[str, T]:
    items = _load_list(path, model)
    return {getattr(item, key_field): item for item in items}


class RulesLoader:
    """Loads and validates all game rule catalogs from JSON data files."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir or DATA_DIR
        self._cache: dict[str, object] = {}

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    # -- Core Mechanics ---

    def ability_modifiers(self) -> list[AbilityModifierEntry]:
        return self._cached("ability_modifiers", lambda: _load_list(
            self._data_dir / "core" / "ability_modifiers.json", AbilityModifierEntry
        ))

    def ability_modifier_for(self, score: int) -> int:
        for entry in self.ability_modifiers():
            if entry.score == score:
                return entry.modifier
        return (score - 10) // 2

    def proficiency_bonuses(self) -> list[ProficiencyBonusEntry]:
        return self._cached("proficiency_bonuses", lambda: _load_list(
            self._data_dir / "core" / "proficiency_bonus.json", ProficiencyBonusEntry
        ))

    def proficiency_bonus_for(self, level: int) -> int:
        for entry in self.proficiency_bonuses():
            if entry.level == level:
                return entry.bonus
        return 2 + (level - 1) // 4

    def skills(self) -> dict[str, SkillEntry]:
        return self._cached("skills", lambda: _load_dict(
            self._data_dir / "core" / "skills.json", SkillEntry, "skill_id"
        ))

    def damage_types(self) -> dict[str, DamageType]:
        return self._cached("damage_types", lambda: _load_dict(
            self._data_dir / "core" / "damage_types.json", DamageType, "damage_type_id"
        ))

    # -- Conditions ---

    def conditions(self) -> dict[str, ConditionEntry]:
        return self._cached("conditions", lambda: _load_dict(
            self._data_dir / "conditions" / "conditions.json", ConditionEntry, "condition_id"
        ))

    def get_condition(self, condition_id: str) -> ConditionEntry | None:
        return self.conditions().get(condition_id)

    def exhaustion_levels(self) -> list[ExhaustionLevel]:
        return self._cached("exhaustion", lambda: _load_list(
            self._data_dir / "conditions" / "exhaustion.json", ExhaustionLevel
        ))

    # -- Combat ---

    def combat_actions(self) -> dict[str, CombatAction]:
        return self._cached("combat_actions", lambda: _load_dict(
            self._data_dir / "combat" / "actions.json", CombatAction, "action_id"
        ))

    def cover_rules(self) -> dict[str, CoverEntry]:
        return self._cached("cover", lambda: _load_dict(
            self._data_dir / "combat" / "cover.json", CoverEntry, "cover_id"
        ))

    def movement_rules(self) -> list[MovementRule]:
        return self._cached("movement", lambda: _load_list(
            self._data_dir / "combat" / "movement.json", MovementRule
        ))

    # -- Equipment ---

    def weapons(self) -> dict[str, WeaponEntry]:
        return self._cached("weapons", lambda: _load_dict(
            self._data_dir / "equipment" / "weapons.json", WeaponEntry, "weapon_id"
        ))

    def get_weapon(self, weapon_id: str) -> WeaponEntry | None:
        return self.weapons().get(weapon_id)

    def armor(self) -> dict[str, ArmorEntry]:
        return self._cached("armor", lambda: _load_dict(
            self._data_dir / "equipment" / "armor.json", ArmorEntry, "armor_id"
        ))

    def get_armor(self, armor_id: str) -> ArmorEntry | None:
        return self.armor().get(armor_id)

    def adventuring_gear(self) -> dict[str, GearEntry]:
        return self._cached("gear", lambda: _load_dict(
            self._data_dir / "equipment" / "adventuring_gear.json", GearEntry, "gear_id"
        ))

    def tools(self) -> dict[str, ToolEntry]:
        return self._cached("tools", lambda: _load_dict(
            self._data_dir / "equipment" / "tools.json", ToolEntry, "tool_id"
        ))

    def mounts(self) -> dict[str, MountEntry]:
        return self._cached("mounts", lambda: _load_dict(
            self._data_dir / "equipment" / "mounts.json", MountEntry, "mount_id"
        ))

    # -- Races ---

    def races(self) -> dict[str, RaceEntry]:
        result: dict[str, RaceEntry] = {}
        races_dir = self._data_dir / "races"
        for path in sorted(races_dir.glob("*.json")):
            if path.stem == "index":
                continue
            race = _load_list(path, RaceEntry)
            for r in race:
                result[r.race_id] = r
        return self._cached("races", lambda: result)

    def get_race(self, race_id: str) -> RaceEntry | None:
        return self.races().get(race_id)

    # -- Classes ---

    def classes(self) -> dict[str, ClassEntry]:
        result: dict[str, ClassEntry] = {}
        classes_dir = self._data_dir / "classes"
        for path in sorted(classes_dir.glob("*.json")):
            if path.stem == "index":
                continue
            entries = _load_list(path, ClassEntry)
            for c in entries:
                result[c.class_id] = c
        return self._cached("classes", lambda: result)

    def get_class(self, class_id: str) -> ClassEntry | None:
        return self.classes().get(class_id)

    # -- Feats & Multiclassing ---

    def feats(self) -> dict[str, FeatEntry]:
        return self._cached("feats", lambda: _load_dict(
            self._data_dir / "customization" / "feats.json", FeatEntry, "feat_id"
        ))

    def get_feat(self, feat_id: str) -> FeatEntry | None:
        return self.feats().get(feat_id)

    def multiclass_requirements(self) -> dict[str, MulticlassRequirement]:
        return self._cached("multiclass", lambda: _load_dict(
            self._data_dir / "customization" / "multiclassing.json",
            MulticlassRequirement, "class_id"
        ))

    # -- Spellcasting ---

    def spellcasting_rules(self) -> list[SpellcastingRule]:
        return self._cached("spellcasting_rules", lambda: _load_list(
            self._data_dir / "spellcasting" / "rules.json", SpellcastingRule
        ))

    def spell_lists(self) -> dict[str, list[str]]:
        raw = _load_json(self._data_dir / "spellcasting" / "spell_lists.json")
        if isinstance(raw, dict):
            return raw  # type: ignore[return-value]
        return {}

    def spells(self) -> dict[str, SpellEntry]:
        if "spells" in self._cache:
            return self._cache["spells"]  # type: ignore[return-value]
        result: dict[str, SpellEntry] = {}
        spells_dir = self._data_dir / "spellcasting" / "spells"
        for path in sorted(spells_dir.glob("*.json")):
            entries = _load_list(path, SpellEntry)
            for s in entries:
                result[s.spell_id] = s
        self._cache["spells"] = result
        return result

    def get_spell(self, spell_id: str) -> SpellEntry | None:
        return self.spells().get(spell_id)

    # -- Cache helper ---

    def _cached(self, key: str, loader: object) -> object:  # type: ignore[type-arg]
        if key not in self._cache:
            self._cache[key] = loader() if callable(loader) else loader
        return self._cache[key]
