"""Inspectable objects registry for the game engine.

Provides the data that the combat resolver uses when resolving inspect actions.
Currently loads the MVP scenario objects; in future this would be per-session.
"""

from __future__ import annotations


def get_inspectable_objects() -> dict[str, dict]:
    """Return the inspectable objects for the current scenario."""
    return {
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
                "hidden_compartment_found": {
                    "dc": 15,
                    "description": (
                        "Your careful examination reveals a loose stone at the altar's base. "
                        "Behind it, a hidden compartment contains a dusty scroll and a small "
                        "vial of glowing liquid."
                    ),
                    "contents": ["scroll_of_protection", "potion_of_healing"],
                },
                "shaman_revealed_weakness": {
                    "dc": 18,
                    "description": (
                        "The runes speak of an ancient binding ritual. Creatures of darkness "
                        "are weakened near this altar — the shaman's magic is less potent here."
                    ),
                    "effect": "shaman_magic_weakened",
                },
            },
        },
    }
