from game_rules.models import SpellEntry

sample = {
    "spell_id": "test",
    "name": "Test",
    "level": 0,
    "school": "evocation",
    "ritual": False,
    "casting_time": {"value": 1, "unit": "action"},
    "range": {"value": None, "unit": "self"},
    "components": {"verbal": True, "somatic": True, "material": None},
    "duration": {"value": 0, "unit": "instantaneous", "concentration": False},
    "effect": {"description": "x"},
    "at_higher_levels": None,
    "classes": [],
    "source_reference": "PHB",
}
SpellEntry.model_validate(sample)
print("ok")
