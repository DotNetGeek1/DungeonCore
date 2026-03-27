"""Tests for the game-rules loader and data integrity."""
from __future__ import annotations

from game_rules import RulesLoader


def _loader() -> RulesLoader:
    return RulesLoader()


class TestCoreData:
    def test_ability_modifiers_count(self) -> None:
        mods = _loader().ability_modifiers()
        assert len(mods) == 30

    def test_ability_modifier_for_10(self) -> None:
        assert _loader().ability_modifier_for(10) == 0

    def test_ability_modifier_for_20(self) -> None:
        assert _loader().ability_modifier_for(20) == 5

    def test_proficiency_bonuses_count(self) -> None:
        bonuses = _loader().proficiency_bonuses()
        assert len(bonuses) == 20

    def test_proficiency_bonus_level_1(self) -> None:
        assert _loader().proficiency_bonus_for(1) == 2

    def test_proficiency_bonus_level_17(self) -> None:
        assert _loader().proficiency_bonus_for(17) == 6

    def test_skills_count(self) -> None:
        skills = _loader().skills()
        assert len(skills) == 18

    def test_damage_types_count(self) -> None:
        dtypes = _loader().damage_types()
        assert len(dtypes) == 13


class TestConditions:
    def test_conditions_count(self) -> None:
        conditions = _loader().conditions()
        assert len(conditions) >= 14

    def test_paralyzed_exists(self) -> None:
        cond = _loader().get_condition("paralyzed")
        assert cond is not None
        assert cond.name == "Paralyzed"

    def test_exhaustion_levels(self) -> None:
        levels = _loader().exhaustion_levels()
        assert len(levels) == 6
        assert levels[5].effect == "Death"


class TestCombat:
    def test_combat_actions_loaded(self) -> None:
        actions = _loader().combat_actions()
        assert "attack" in actions
        assert "dodge" in actions

    def test_cover_rules(self) -> None:
        cover = _loader().cover_rules()
        assert "half" in cover
        assert cover["half"].ac_bonus == 2

    def test_movement_rules(self) -> None:
        rules = _loader().movement_rules()
        assert len(rules) > 0


class TestEquipment:
    def test_weapons_count(self) -> None:
        weapons = _loader().weapons()
        assert len(weapons) >= 37

    def test_longsword(self) -> None:
        w = _loader().get_weapon("longsword")
        assert w is not None
        assert w.damage_dice == "1d8"
        assert w.damage_type == "slashing"

    def test_armor_count(self) -> None:
        armor = _loader().armor()
        assert len(armor) >= 13

    def test_plate_armor(self) -> None:
        a = _loader().get_armor("plate")
        assert a is not None
        assert a.base_ac == 18
        assert a.dex_modifier is False

    def test_adventuring_gear_loaded(self) -> None:
        gear = _loader().adventuring_gear()
        assert len(gear) > 50

    def test_tools_loaded(self) -> None:
        tools = _loader().tools()
        assert len(tools) > 30

    def test_mounts_loaded(self) -> None:
        mounts = _loader().mounts()
        assert len(mounts) > 10


class TestRaces:
    def test_races_count(self) -> None:
        races = _loader().races()
        assert len(races) >= 9

    def test_dwarf_exists(self) -> None:
        dwarf = _loader().get_race("dwarf")
        assert dwarf is not None
        assert dwarf.speed == 25


class TestClasses:
    def test_classes_count(self) -> None:
        classes = _loader().classes()
        assert len(classes) >= 12

    def test_fighter_exists(self) -> None:
        fighter = _loader().get_class("fighter")
        assert fighter is not None
        assert fighter.hit_die in ("d10", "1d10")


class TestCustomization:
    def test_feats_count(self) -> None:
        feats = _loader().feats()
        assert len(feats) >= 40

    def test_multiclass_requirements(self) -> None:
        mc = _loader().multiclass_requirements()
        assert len(mc) == 12


class TestSpellcasting:
    def test_spellcasting_rules_loaded(self) -> None:
        rules = _loader().spellcasting_rules()
        assert len(rules) > 0

    def test_spell_lists_loaded(self) -> None:
        lists = _loader().spell_lists()
        assert "wizard" in lists
        assert "cleric" in lists

    def test_spells_loaded(self) -> None:
        spells = _loader().spells()
        assert len(spells) > 200

    def test_fireball(self) -> None:
        fb = _loader().get_spell("fireball")
        assert fb is not None
        assert fb.level == 3
        assert fb.school == "evocation"
