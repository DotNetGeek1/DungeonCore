from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class RuleBaseModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
    )


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Ability(StrEnum):
    STR = "STR"
    DEX = "DEX"
    CON = "CON"
    INT = "INT"
    WIS = "WIS"
    CHA = "CHA"


class ArmorCategory(StrEnum):
    LIGHT = "light"
    MEDIUM = "medium"
    HEAVY = "heavy"
    SHIELD = "shield"


class WeaponCategory(StrEnum):
    SIMPLE_MELEE = "simple_melee"
    SIMPLE_RANGED = "simple_ranged"
    MARTIAL_MELEE = "martial_melee"
    MARTIAL_RANGED = "martial_ranged"


class SpellSchool(StrEnum):
    ABJURATION = "abjuration"
    CONJURATION = "conjuration"
    DIVINATION = "divination"
    ENCHANTMENT = "enchantment"
    EVOCATION = "evocation"
    ILLUSION = "illusion"
    NECROMANCY = "necromancy"
    TRANSMUTATION = "transmutation"


class CreatureSize(StrEnum):
    TINY = "Tiny"
    SMALL = "Small"
    MEDIUM = "Medium"
    LARGE = "Large"
    HUGE = "Huge"
    GARGANTUAN = "Gargantuan"


NonEmptyStr = Annotated[str, Field(min_length=1)]


# ---------------------------------------------------------------------------
# Core Mechanics
# ---------------------------------------------------------------------------

class AbilityModifierEntry(RuleBaseModel):
    score: int
    modifier: int


class ProficiencyBonusEntry(RuleBaseModel):
    level: int
    bonus: int


class SkillEntry(RuleBaseModel):
    skill_id: NonEmptyStr
    name: NonEmptyStr
    ability: Ability


class DamageType(RuleBaseModel):
    damage_type_id: NonEmptyStr
    name: NonEmptyStr
    description: str = ""


# ---------------------------------------------------------------------------
# Conditions
# ---------------------------------------------------------------------------

class ConditionEffect(RuleBaseModel):
    type: NonEmptyStr
    value: bool | int | str | list[str] | None = None
    condition: str | None = None
    abilities: list[str] | None = None


class ConditionEntry(RuleBaseModel):
    condition_id: NonEmptyStr
    name: NonEmptyStr
    effects: list[ConditionEffect]
    source_reference: str = ""


class ExhaustionLevel(RuleBaseModel):
    level: int
    effect: NonEmptyStr


# ---------------------------------------------------------------------------
# Combat
# ---------------------------------------------------------------------------

class CombatAction(RuleBaseModel):
    action_id: NonEmptyStr
    name: NonEmptyStr
    cost: NonEmptyStr
    description: str


class CoverEntry(RuleBaseModel):
    cover_id: NonEmptyStr
    name: NonEmptyStr
    ac_bonus: int
    dex_save_bonus: int
    description: str = ""


class MovementRule(RuleBaseModel):
    rule_id: NonEmptyStr
    name: NonEmptyStr
    description: str
    cost_multiplier: float | None = None


# ---------------------------------------------------------------------------
# Equipment: Weapons
# ---------------------------------------------------------------------------

class WeaponRange(RuleBaseModel):
    normal: int
    long: int


class WeaponEntry(RuleBaseModel):
    weapon_id: NonEmptyStr
    name: NonEmptyStr
    category: WeaponCategory
    cost: str
    damage_dice: str
    damage_type: NonEmptyStr
    weight: str
    properties: list[str] = Field(default_factory=list)
    range: WeaponRange | None = None


# ---------------------------------------------------------------------------
# Equipment: Armor
# ---------------------------------------------------------------------------

class ArmorEntry(RuleBaseModel):
    armor_id: NonEmptyStr
    name: NonEmptyStr
    category: ArmorCategory
    cost: str
    base_ac: int
    dex_modifier: bool = True
    max_dex_bonus: int | None = None
    strength_requirement: int | None = None
    stealth_disadvantage: bool = False
    weight: str


# ---------------------------------------------------------------------------
# Equipment: Gear, Tools, Mounts
# ---------------------------------------------------------------------------

class GearEntry(RuleBaseModel):
    gear_id: NonEmptyStr
    name: NonEmptyStr
    cost: str
    weight: str = ""
    description: str = ""


class ToolEntry(RuleBaseModel):
    tool_id: NonEmptyStr
    name: NonEmptyStr
    category: NonEmptyStr
    cost: str
    weight: str = ""


class MountEntry(RuleBaseModel):
    mount_id: NonEmptyStr
    name: NonEmptyStr
    cost: str
    speed: str
    carrying_capacity: str = ""


# ---------------------------------------------------------------------------
# Races
# ---------------------------------------------------------------------------

class RacialTrait(RuleBaseModel):
    trait_id: NonEmptyStr
    name: NonEmptyStr
    description: str


class SubraceEntry(RuleBaseModel):
    subrace_id: NonEmptyStr
    name: NonEmptyStr
    ability_score_increase: dict[str, int] = Field(default_factory=dict)
    traits: list[RacialTrait] = Field(default_factory=list)


class RaceEntry(RuleBaseModel):
    race_id: NonEmptyStr
    name: NonEmptyStr
    ability_score_increase: dict[str, int]
    size: CreatureSize
    speed: int
    languages: list[str] = Field(default_factory=list)
    traits: list[RacialTrait] = Field(default_factory=list)
    subraces: list[SubraceEntry] = Field(default_factory=list)
    source_reference: str = ""


# ---------------------------------------------------------------------------
# Classes
# ---------------------------------------------------------------------------

class ClassFeature(RuleBaseModel):
    feature_id: NonEmptyStr
    name: NonEmptyStr
    level: int
    description: str
    usage: dict[str, str | int] | None = None


class SubclassEntry(RuleBaseModel):
    subclass_id: NonEmptyStr
    name: NonEmptyStr
    description: str = ""
    features: list[ClassFeature] = Field(default_factory=list)


class ClassEntry(RuleBaseModel):
    class_id: NonEmptyStr
    name: NonEmptyStr
    hit_die: NonEmptyStr
    primary_ability: list[str]
    saving_throws: list[str]
    armor_proficiencies: list[str] = Field(default_factory=list)
    weapon_proficiencies: list[str] = Field(default_factory=list)
    tool_proficiencies: list[str] = Field(default_factory=list)
    skill_choices: list[str] = Field(default_factory=list)
    num_skill_choices: int = 2
    features: list[ClassFeature] = Field(default_factory=list)
    subclass_label: str = ""
    subclass_level: int = 3
    subclasses: list[SubclassEntry] = Field(default_factory=list)
    spellcasting: dict[str, str | int | bool] | None = None
    source_reference: str = ""


# ---------------------------------------------------------------------------
# Feats & Multiclassing
# ---------------------------------------------------------------------------

class FeatEntry(RuleBaseModel):
    feat_id: NonEmptyStr
    name: NonEmptyStr
    prerequisite: str | None = None
    benefits: list[str]
    source_reference: str = ""


class MulticlassRequirement(RuleBaseModel):
    class_id: NonEmptyStr
    ability_minimums: dict[str, int]
    proficiencies_gained: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Spellcasting
# ---------------------------------------------------------------------------

class CastingTime(RuleBaseModel):
    value: int
    unit: NonEmptyStr


class SpellRange(RuleBaseModel):
    value: int | None = None
    unit: NonEmptyStr


class MaterialComponent(RuleBaseModel):
    description: str
    cost: str | None = None
    consumed: bool = False


class SpellComponents(RuleBaseModel):
    verbal: bool = False
    somatic: bool = False
    material: MaterialComponent | None = None


class SpellDuration(RuleBaseModel):
    value: int = 0
    unit: NonEmptyStr
    concentration: bool = False


class SpellEffect(RuleBaseModel):
    description: str = ""
    damage_dice: str | None = None
    damage_type: str | None = None
    healing_dice: str | None = None
    area_shape: str | None = None
    area_size: int | None = None
    save_ability: str | None = None
    save_effect_on_success: str | None = None
    attack_type: str | None = None


class SpellEntry(RuleBaseModel):
    spell_id: NonEmptyStr
    name: NonEmptyStr
    level: int = Field(ge=0, le=9)
    school: SpellSchool
    ritual: bool = False
    casting_time: CastingTime
    range: SpellRange
    components: SpellComponents
    duration: SpellDuration
    effect: SpellEffect
    at_higher_levels: str | None = None
    classes: list[str] = Field(default_factory=list)
    source_reference: str = ""


class SpellcastingRule(RuleBaseModel):
    rule_id: NonEmptyStr
    name: NonEmptyStr
    description: str
