"""
Randomised search over Policy parameter space.

This is intentionally simple: sample N random policies, simulate each,
keep the best (lowest goal-time). The search is the optimisation; the
simulator is the source of truth.
"""

import random
from dataclasses import replace
from typing import Optional

from . import policy as pol


def random_policy(rng: random.Random) -> pol.Policy:
    # Starting split: usually all 3 on food, occasionally 2+1 onto wood.
    if rng.random() < 0.25:
        sf, sw = 2, 1
    else:
        sf, sw = 3, 0

    # Per-villager assignment plan. We do this in chunks: first M villagers
    # to food (build the eco), then a wood block, then mixed.
    food_block = rng.randint(4, 10)
    wood_block = rng.randint(3, 8)
    food_block2 = rng.randint(2, 8)
    gold_block = rng.randint(0, 4)  # before Castle click, usually 0
    plan = (["food"] * food_block
            + ["wood"] * wood_block
            + ["food"] * food_block2
            + ["gold"] * gold_block
            + ["food"] * 20)

    barracks_at = rng.randint(15, 22)
    feudal_at = rng.randint(max(barracks_at, 18), 24)
    stable_at = rng.randint(feudal_at, feudal_at + 4)
    second_at = rng.randint(stable_at, stable_at + 4)
    castle_lo = max(second_at + 1, 24)
    castle_hi = max(castle_lo + 2, 34)
    castle_at = rng.randint(castle_lo, castle_hi)
    second_bldg = rng.choice(["archery_range", "blacksmith"])
    gold_for_castle = rng.randint(4, 9)
    min_wood = rng.randint(3, 5)

    return pol.Policy(
        start_food=sf, start_wood=sw, start_gold=0, start_stone=0,
        assignments=plan,
        build_barracks_at_vils=barracks_at,
        click_feudal_at_vils=feudal_at,
        build_stable_at_vils=stable_at,
        build_second_feudal_at_vils=second_at,
        second_feudal_building=second_bldg,
        click_castle_at_vils=castle_at,
        gold_villagers_for_castle=gold_for_castle,
        min_wood_villagers=min_wood,
    )


def score(state) -> int:
    """Lower is better. Huge penalty if the goal wasn't reached."""
    from . import policy as pol_mod
    if pol_mod.goal_reached(state):
        return state.t
    return 10**6 + state.t


def search(samples: int = 2000, seed: int = 0,
           max_seconds: int = 30 * 60) -> tuple:
    """Returns (best_policy, best_state, best_score)."""
    rng = random.Random(seed)
    best = None  # (score, policy, state)
    for i in range(samples):
        p = random_policy(rng)
        st = pol.run(p, max_seconds=max_seconds)
        sc = score(st)
        if best is None or sc < best[0]:
            best = (sc, p, st)
    return best[1], best[2], best[0]


def local_refine(base: pol.Policy, iterations: int = 200, seed: int = 1,
                 max_seconds: int = 30 * 60) -> tuple:
    """Hill-climb around `base` by perturbing one parameter at a time."""
    rng = random.Random(seed)
    cur_state = pol.run(base, max_seconds=max_seconds)
    cur_score = score(cur_state)
    cur = base
    for _ in range(iterations):
        cand = _perturb(cur, rng)
        st = pol.run(cand, max_seconds=max_seconds)
        sc = score(st)
        if sc < cur_score:
            cur, cur_score, cur_state = cand, sc, st
    return cur, cur_state, cur_score


def _perturb(p: pol.Policy, rng: random.Random) -> pol.Policy:
    fields_int = [
        "build_barracks_at_vils",
        "click_feudal_at_vils",
        "build_stable_at_vils",
        "build_second_feudal_at_vils",
        "click_castle_at_vils",
        "gold_villagers_for_castle",
        "min_wood_villagers",
    ]
    field = rng.choice(fields_int)
    delta = rng.choice([-2, -1, 1, 2])
    new_val = max(1, getattr(p, field) + delta)
    updates = {field: new_val}
    # Keep ordering sane.
    updated = replace(p, **updates)
    if updated.click_feudal_at_vils < updated.build_barracks_at_vils:
        updated = replace(updated,
                          click_feudal_at_vils=updated.build_barracks_at_vils)
    if updated.build_stable_at_vils < updated.click_feudal_at_vils:
        updated = replace(updated,
                          build_stable_at_vils=updated.click_feudal_at_vils)
    if updated.build_second_feudal_at_vils < updated.build_stable_at_vils:
        updated = replace(updated,
                          build_second_feudal_at_vils=updated.build_stable_at_vils)
    if updated.click_castle_at_vils < updated.build_second_feudal_at_vils + 1:
        updated = replace(updated,
                          click_castle_at_vils=updated.build_second_feudal_at_vils + 1)
    return updated
