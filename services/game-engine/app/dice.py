from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class DiceRoll:
    die: str
    value: int
    modifier: int = 0

    @property
    def total(self) -> int:
        return self.value + self.modifier


@dataclass
class DiceRoller:
    seed: int | None = None
    _rng: random.Random = field(init=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    def roll(self, die: str, modifier: int = 0) -> DiceRoll:
        if die.startswith("d"):
            sides = int(die[1:])
        else:
            sides = int(die)

        value = self._rng.randint(1, sides)
        return DiceRoll(die=f"d{sides}", value=value, modifier=modifier)

    def roll_d20(self, modifier: int = 0) -> DiceRoll:
        return self.roll("d20", modifier)

    def roll_damage(self, die: str, count: int = 1, modifier: int = 0) -> list[DiceRoll]:
        rolls = [self.roll(die) for _ in range(count)]
        if modifier and rolls:
            rolls[-1] = DiceRoll(die=rolls[-1].die, value=rolls[-1].value, modifier=modifier)
        return rolls

    def roll_with_advantage(self, modifier: int = 0) -> tuple[DiceRoll, DiceRoll, DiceRoll]:
        roll1 = self.roll_d20(modifier)
        roll2 = self.roll_d20(modifier)
        best = roll1 if roll1.total >= roll2.total else roll2
        return roll1, roll2, best

    def roll_with_disadvantage(self, modifier: int = 0) -> tuple[DiceRoll, DiceRoll, DiceRoll]:
        roll1 = self.roll_d20(modifier)
        roll2 = self.roll_d20(modifier)
        worst = roll1 if roll1.total <= roll2.total else roll2
        return roll1, roll2, worst

    def reset(self, seed: int | None = None) -> None:
        self.seed = seed
        self._rng = random.Random(seed)


_default_roller: DiceRoller | None = None


def get_dice_roller(seed: int | None = None) -> DiceRoller:
    global _default_roller
    if _default_roller is None or seed is not None:
        _default_roller = DiceRoller(seed=seed)
    return _default_roller


def roll_d20(modifier: int = 0, seed: int | None = None) -> DiceRoll:
    roller = get_dice_roller(seed)
    return roller.roll_d20(modifier)


def roll_damage(die: str, count: int = 1, modifier: int = 0, seed: int | None = None) -> list[DiceRoll]:
    roller = get_dice_roller(seed)
    return roller.roll_damage(die, count, modifier)
