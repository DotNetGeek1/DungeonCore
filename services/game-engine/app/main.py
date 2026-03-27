import logging
from contextlib import asynccontextmanager
from typing import Annotated, AsyncGenerator, Literal

import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException, Request, status
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from shared_config.connections import (
    check_postgres_health,
    check_rabbitmq_health,
    check_redis_health,
)
from shared_config.settings import ServiceSettings
from shared_schemas.actions import (
    ActionUnion,
    AttackAction,
    CastSpellBasicAction,
    DefendAction,
    InspectAction,
    InteractAction,
    MoveAction,
    MoveAndAttackAction,
)
from shared_schemas.enums import ActionType
from shared_schemas.state import GameState

from game_rules import RulesLoader

from .dice import DiceRoll, DiceRoller, get_dice_roller
from .inspectable_objects import get_inspectable_objects
from .resolution.combat import CombatResolver, ResolutionResult, StatePatch
from .validators import (
    AttackValidator,
    CastSpellValidator,
    DefendValidator,
    InspectValidator,
    InteractValidator,
    MoveAndAttackValidator,
    MoveValidator,
    ValidationResult,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings: ServiceSettings = app.state.settings
    logger.info("Starting %s on port %d", settings.service_name, settings.port)

    rules = RulesLoader()
    app.state.rules = rules

    app.state.dice_roller = DiceRoller(seed=None)
    app.state.inspectable_objects = get_inspectable_objects()
    app.state.combat_resolver = CombatResolver(
        app.state.dice_roller, rules=rules, inspectable_objects=app.state.inspectable_objects,
    )

    app.state.validators = {
        ActionType.ATTACK: AttackValidator(),
        ActionType.MOVE: MoveValidator(),
        ActionType.MOVE_AND_ATTACK: MoveAndAttackValidator(),
        ActionType.DEFEND: DefendValidator(),
        ActionType.INSPECT: InspectValidator(),
        ActionType.INTERACT: InteractValidator(),
        ActionType.CAST_SPELL_BASIC: CastSpellValidator(rules=rules),
    }

    yield

    logger.info("Shutting down %s", settings.service_name)


def create_app(settings: ServiceSettings | None = None) -> FastAPI:
    if settings is None:
        settings = ServiceSettings.for_service("game-engine", 8003)

    app = FastAPI(
        title="DungeonCore Game Engine",
        description="Deterministic game rules and resolution engine",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = settings

    router = APIRouter()

    class DependencyStatus(BaseModel):
        postgres: bool
        redis: bool
        rabbitmq: bool

    class HealthResponse(BaseModel):
        service: str
        status: Literal["ok", "degraded"]
        port: int
        dependencies: DependencyStatus

    @router.get("/health", response_model=HealthResponse)
    async def health_check(request: Request) -> HealthResponse:
        settings: ServiceSettings = request.app.state.settings
        deps = DependencyStatus(
            postgres=check_postgres_health(settings),
            redis=check_redis_health(settings),
            rabbitmq=check_rabbitmq_health(settings),
        )
        all_healthy = deps.postgres and deps.redis and deps.rabbitmq
        return HealthResponse(
            service=settings.service_name,
            status="ok" if all_healthy else "degraded",
            port=settings.port,
            dependencies=deps,
        )

    class ValidateActionRequest(BaseModel):
        action: ActionUnion
        actor_id: str
        state: GameState

    class ValidateActionResponse(BaseModel):
        valid: bool
        errors: list[str] = Field(default_factory=list)
        warnings: list[str] = Field(default_factory=list)

    @router.post("/validate", response_model=ValidateActionResponse)
    async def validate_action(request: Request, body: ValidateActionRequest) -> ValidateActionResponse:
        logger.debug("Validating action type=%s actor_id=%s", body.action.type, body.actor_id)
        validators = request.app.state.validators
        validator = validators.get(body.action.type)

        if validator is None:
            logger.warning("No validator for action type: %s", body.action.type)
            return ValidateActionResponse(
                valid=False,
                errors=[f"No validator for action type: {body.action.type}"],
            )

        result = validator.validate(body.action, body.actor_id, body.state)
        if not result.valid:
            logger.info("Validation failed for %s: %s", body.action.type, result.errors)
        return ValidateActionResponse(
            valid=result.valid,
            errors=result.errors,
            warnings=result.warnings,
        )

    class DiceRollResponse(BaseModel):
        die: str
        value: int
        modifier: int
        total: int

    class ResolveActionRequest(BaseModel):
        action: ActionUnion
        actor_id: str
        state: GameState
        seed: int | None = None

    class StatePatchResponse(BaseModel):
        patch_type: str
        target_id: str
        field: str
        old_value: object
        new_value: object

    class ResolveActionResponse(BaseModel):
        success: bool
        action_type: ActionType
        description: str
        dice_rolls: list[DiceRollResponse] = Field(default_factory=list)
        state_patches: list[StatePatchResponse] = Field(default_factory=list)
        hit: bool | None = None
        damage: int | None = None

    @router.post("/resolve", response_model=ResolveActionResponse)
    async def resolve_action(request: Request, body: ResolveActionRequest) -> ResolveActionResponse:
        logger.info("Resolving action type=%s actor_id=%s", body.action.type, body.actor_id)
        validators = request.app.state.validators
        validator = validators.get(body.action.type)

        if validator is not None:
            validation = validator.validate(body.action, body.actor_id, body.state)
            if not validation.valid:
                logger.warning(
                    "Resolution rejected - validation failed for %s: %s",
                    body.action.type,
                    validation.errors,
                )
                return ResolveActionResponse(
                    success=False,
                    action_type=body.action.type,
                    description=f"Validation failed: {', '.join(validation.errors)}",
                )

        if body.seed is not None:
            resolver = CombatResolver(
                DiceRoller(seed=body.seed),
                rules=request.app.state.rules,
                inspectable_objects=request.app.state.inspectable_objects,
            )
        else:
            resolver = request.app.state.combat_resolver

        result = resolver.resolve(body.action, body.actor_id, body.state)

        logger.info(
            "Resolved %s: success=%s description=%s",
            result.action_type,
            result.success,
            result.description,
        )
        if result.dice_rolls:
            logger.debug("Dice rolls: %s", [(r.die, r.total) for r in result.dice_rolls])
        if result.state_patches:
            logger.debug("State patches: %d changes", len(result.state_patches))

        return ResolveActionResponse(
            success=result.success,
            action_type=result.action_type,
            description=result.description,
            dice_rolls=[
                DiceRollResponse(
                    die=roll.die,
                    value=roll.value,
                    modifier=roll.modifier,
                    total=roll.total,
                )
                for roll in result.dice_rolls
            ],
            state_patches=[
                StatePatchResponse(
                    patch_type=patch.patch_type,
                    target_id=patch.target_id,
                    field=patch.field,
                    old_value=patch.old_value,
                    new_value=patch.new_value,
                )
                for patch in result.state_patches
            ],
            hit=result.hit,
            damage=result.damage,
        )

    class RollDiceRequest(BaseModel):
        die: str = "d20"
        modifier: int = 0
        count: int = 1
        seed: int | None = None

    class RollDiceResponse(BaseModel):
        rolls: list[DiceRollResponse]
        total: int

    @router.post("/roll", response_model=RollDiceResponse)
    async def roll_dice(request: Request, body: RollDiceRequest) -> RollDiceResponse:
        logger.debug("Rolling %dx%s modifier=%d", body.count, body.die, body.modifier)
        roller = DiceRoller(seed=body.seed) if body.seed else request.app.state.dice_roller

        rolls = []
        for i in range(body.count):
            mod = body.modifier if i == body.count - 1 else 0
            roll = roller.roll(body.die, mod)
            rolls.append(
                DiceRollResponse(
                    die=roll.die,
                    value=roll.value,
                    modifier=roll.modifier,
                    total=roll.total,
                )
            )

        total = sum(r.total for r in rolls)
        logger.debug("Roll result: %s = %d", [r.total for r in rolls], total)
        return RollDiceResponse(
            rolls=rolls,
            total=total,
        )

    # --- Rules data endpoints ---

    @router.get("/rules/weapons")
    async def list_weapons(request: Request) -> dict:
        """List all weapons from the game rules."""
        rl: RulesLoader = request.app.state.rules
        weapons = rl.weapons()
        return {
            "weapons": [
                {
                    "weapon_id": w.weapon_id,
                    "name": w.name,
                    "category": w.category,
                    "damage_dice": w.damage_dice,
                    "damage_type": w.damage_type,
                    "properties": w.properties,
                    "weight": w.weight,
                }
                for w in weapons.values()
            ],
            "total": len(weapons),
        }

    @router.get("/rules/weapons/{weapon_id}")
    async def get_weapon(request: Request, weapon_id: str) -> dict:
        rl: RulesLoader = request.app.state.rules
        weapon = rl.get_weapon(weapon_id)
        if weapon is None:
            raise HTTPException(status_code=404, detail=f"Weapon '{weapon_id}' not found")
        return weapon.model_dump()

    @router.get("/rules/spells")
    async def list_spells(
        request: Request,
        level: int | None = None,
        school: str | None = None,
    ) -> dict:
        """List spells, optionally filtered by level or school."""
        rl: RulesLoader = request.app.state.rules
        spells = list(rl.spells().values())

        if level is not None:
            spells = [s for s in spells if s.level == level]
        if school:
            spells = [s for s in spells if s.school.lower() == school.lower()]

        return {
            "spells": [
                {
                    "spell_id": s.spell_id,
                    "name": s.name,
                    "level": s.level,
                    "school": s.school,
                    "ritual": s.ritual,
                    "classes": s.classes,
                }
                for s in spells
            ],
            "total": len(spells),
        }

    @router.get("/rules/spells/{spell_id}")
    async def get_spell(request: Request, spell_id: str) -> dict:
        rl: RulesLoader = request.app.state.rules
        spell = rl.get_spell(spell_id)
        if spell is None:
            raise HTTPException(status_code=404, detail=f"Spell '{spell_id}' not found")
        return spell.model_dump()

    @router.get("/rules/conditions")
    async def list_conditions(request: Request) -> dict:
        """List all conditions from the game rules."""
        rl: RulesLoader = request.app.state.rules
        conditions = rl.conditions()
        return {
            "conditions": [
                {"condition_id": c.condition_id, "name": c.name}
                for c in conditions.values()
            ],
            "total": len(conditions),
        }

    @router.get("/rules/conditions/{condition_id}")
    async def get_condition(request: Request, condition_id: str) -> dict:
        rl: RulesLoader = request.app.state.rules
        condition = rl.get_condition(condition_id)
        if condition is None:
            raise HTTPException(status_code=404, detail=f"Condition '{condition_id}' not found")
        return condition.model_dump()

    @router.get("/rules/classes")
    async def list_classes(request: Request) -> dict:
        """List all character classes from the game rules."""
        rl: RulesLoader = request.app.state.rules
        classes = rl.classes()
        return {
            "classes": [
                {
                    "class_id": c.class_id,
                    "name": c.name,
                    "hit_die": c.hit_die,
                    "primary_ability": c.primary_ability,
                }
                for c in classes.values()
            ],
            "total": len(classes),
        }

    @router.get("/rules/classes/{class_id}")
    async def get_class(request: Request, class_id: str) -> dict:
        rl: RulesLoader = request.app.state.rules
        cls = rl.get_class(class_id)
        if cls is None:
            raise HTTPException(status_code=404, detail=f"Class '{class_id}' not found")
        return cls.model_dump()

    @router.get("/rules/armor")
    async def list_armor(request: Request) -> dict:
        """List all armor from the game rules."""
        rl: RulesLoader = request.app.state.rules
        armor = rl.armor()
        return {
            "armor": [
                {
                    "armor_id": a.armor_id,
                    "name": a.name,
                    "category": a.category,
                    "base_ac": a.base_ac,
                    "weight": a.weight,
                }
                for a in armor.values()
            ],
            "total": len(armor),
        }

    @router.get("/rules/races")
    async def list_races(request: Request) -> dict:
        """List all races from the game rules."""
        rl: RulesLoader = request.app.state.rules
        races = rl.races()
        return {
            "races": [
                {
                    "race_id": r.race_id,
                    "name": r.name,
                    "size": r.size,
                    "speed": r.speed,
                }
                for r in races.values()
            ],
            "total": len(races),
        }

    app.include_router(router, tags=["game-engine"])

    return app


def main() -> None:
    settings = ServiceSettings.for_service("game-engine", 8003)
    app = create_app(settings)
    uvicorn.run(app, host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
