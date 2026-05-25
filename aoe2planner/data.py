"""
Generic-civ game constants for AoE2 (Definitive Edition baseline).

Sources:
- Unit/building/tech costs and times: aoe2techtree.net, in-game values
- Effective gather rates: SOTL community measurements (per-villager,
  averaged including walking + dropoff). These already fold in walking
  losses, so we do NOT separately simulate dropoff distance.

Simplifications (v1, generic civ):
- One effective rate per resource type (no berry vs sheep vs boar split).
- Drop-off buildings (lumber camp, mining camp, mill) modelled as a flat
  one-time wood cost the first time a villager is assigned to that
  resource, with no build-time delay (rate already accounts for it).
- All buildings built by exactly one villager at base build time.
- No civ bonuses, no techs that change rates (loom, wheelbarrow, etc.).
"""

from dataclasses import dataclass


# Starting conditions (standard random map, DE)
START_FOOD = 200
START_WOOD = 200
START_GOLD = 100
START_STONE = 200
START_VILLAGERS = 3
START_SCOUT_POP = 1  # 1 scout cavalry counts toward pop
TC_POP_PROVIDED = 5
HOUSE_POP_PROVIDED = 5
POP_MAX = 200

# Effective gather rates (resources per second per villager).
# These bake in walking, drop-off, and average resource type within a category.
GATHER_RATE = {
    "food": 0.33,   # mixed sheep/boar/berries/farms in dark age
    "wood": 0.39,
    "gold": 0.38,
    "stone": 0.36,
}

# One-time dropoff building cost charged the first time a villager
# is assigned to gather that resource. Food is treated as "free" in v1
# (sheep/berries don't strictly need a mill).
DROPOFF_WOOD_COST = {
    "food": 0,
    "wood": 100,   # lumber camp
    "gold": 100,   # mining camp
    "stone": 100,  # mining camp
}


@dataclass(frozen=True)
class UnitDef:
    food: int = 0
    wood: int = 0
    gold: int = 0
    stone: int = 0
    build_time: int = 0   # seconds at TC / production building
    pop_cost: int = 1


@dataclass(frozen=True)
class BuildingDef:
    food: int = 0
    wood: int = 0
    gold: int = 0
    stone: int = 0
    build_time: int = 0   # seconds with 1 villager


@dataclass(frozen=True)
class TechDef:
    food: int = 0
    wood: int = 0
    gold: int = 0
    stone: int = 0
    research_time: int = 0


VILLAGER = UnitDef(food=50, build_time=25, pop_cost=1)

BUILDINGS = {
    "house":         BuildingDef(wood=25,  build_time=25),
    "barracks":      BuildingDef(wood=175, build_time=50),
    "stable":        BuildingDef(wood=175, build_time=50),
    "archery_range": BuildingDef(wood=175, build_time=50),
    "blacksmith":    BuildingDef(wood=150, build_time=40),
}

# Age-up "techs" researched at the Town Center.
FEUDAL_AGE = TechDef(food=500, research_time=130)
CASTLE_AGE = TechDef(food=800, gold=200, research_time=160)

# Prerequisites: number of buildings of the previous age required.
# Generic: 1 Dark-Age building to click Feudal, 2 Feudal-Age buildings
# to click Castle. (TC does not count.)
DARK_AGE_BUILDINGS = {"barracks"}
FEUDAL_AGE_BUILDINGS = {"stable", "archery_range", "blacksmith"}
