"""
Parameterised build-order policy.

A `Policy` is a small, fully-determined recipe describing:
- how to distribute the starting 3 villagers,
- where each newly-trained villager should go (food / wood / gold / stone),
- when to build the required age-prerequisite buildings,
- when to click Feudal and Castle,
- when to (re)balance villagers onto gold for the Castle click.

The search layer treats Policy fields as the variables to optimise.
"""

from dataclasses import dataclass, field
from typing import Optional

from . import data, sim


@dataclass
class Policy:
    # Where the starting 3 villagers go (must sum to 3).
    start_food: int = 3
    start_wood: int = 0
    start_gold: int = 0
    start_stone: int = 0

    # Per-new-villager assignment. Index 0 = the 4th villager overall.
    # If the list is shorter than the number trained, the last entry repeats.
    assignments: list = field(default_factory=lambda: ["food"] * 30)

    # Trigger thresholds, measured in *total villagers existing* (alive,
    # not counting the scout). The action fires the first tick the
    # condition becomes true.
    build_barracks_at_vils: int = 19      # need 1 dark-age building
    click_feudal_at_vils: int = 22
    build_stable_at_vils: int = 23        # 1st feudal building
    build_second_feudal_at_vils: int = 24
    second_feudal_building: str = "archery_range"  # or "blacksmith"
    click_castle_at_vils: int = 28

    # When clicking Feudal/Castle, optionally rebalance villagers from
    # other jobs onto gold (Castle costs 200 gold).
    gold_villagers_for_castle: int = 6

    # Soft floor on wood villagers so building costs and houses can be paid.
    min_wood_villagers: int = 4

    def assignment_for_vil(self, vil_index_from_4: int) -> str:
        if not self.assignments:
            return "food"
        i = min(vil_index_from_4, len(self.assignments) - 1)
        return self.assignments[i]


# --- helpers ---

def _maybe_build_house(s: sim.State) -> None:
    """Queue a house if pop will hit the cap soon and we can afford it."""
    # Rough heuristic: any in-progress vil + current pop close to cap.
    projected = s.pop_used  # already includes queued
    in_progress_houses = sum(1 for b in s.in_progress if b.name == "house")
    future_cap = s.pop_cap + in_progress_houses * data.HOUSE_POP_PROVIDED
    if projected + 2 >= future_cap and future_cap < data.POP_MAX:
        # Pull a wood villager to build it.
        sim.start_building(s, "house", "wood")


def _next_villager_index(trained_so_far: int) -> int:
    """Index into Policy.assignments for the next villager to be trained."""
    return trained_so_far


def _assign_new_villagers(s: sim.State, policy: Policy, trained_after_start: int) -> int:
    """Send every idle (already-counted) villager to its policy-assigned job.
    Returns updated `trained_after_start` counter.
    """
    while s.villagers["idle"] > 0:
        job = policy.assignment_for_vil(trained_after_start)
        # If we want to honour min_wood early, divert.
        if (job != "wood"
                and s.villagers["wood"] < policy.min_wood_villagers
                and s.t < 60):
            job = "wood"
        ok = sim.assign_idle_villager(s, job)
        if not ok:
            # Couldn't afford dropoff; park on food instead.
            sim.assign_idle_villager(s, "food")
        trained_after_start += 1
    return trained_after_start


def _rebalance_for_castle(s: sim.State, policy: Policy) -> None:
    """Make sure we have enough gold villagers heading into Castle click."""
    have_gold = s.villagers["gold"]
    want = policy.gold_villagers_for_castle
    if have_gold >= want:
        return
    need = want - have_gold
    # Pull from food first (food no longer the bottleneck once Castle clicked),
    # then wood.
    for src in ("food", "wood"):
        while need > 0 and s.villagers[src] > 1:
            if sim.reassign_villager(s, src, "gold"):
                need -= 1
            else:
                break


# --- main driver ---

def run(policy: Policy, max_seconds: int = 30 * 60, verbose: bool = False) -> sim.State:
    """Simulate the policy until the goal is reached or `max_seconds` elapses.

    Goal: Castle Age researched AND >=1 Barracks AND >=1 Stable AND >=1 of
    {archery_range, blacksmith} exist.
    """
    s = sim.new_state()

    # Initial split of the 3 starting villagers.
    splits = [
        ("food", policy.start_food),
        ("wood", policy.start_wood),
        ("gold", policy.start_gold),
        ("stone", policy.start_stone),
    ]
    for job, count in splits:
        for _ in range(count):
            sim.assign_idle_villager(s, job)

    trained_after_start = 0  # how many villagers trained beyond the initial 3
    castle_rebalance_done = False

    while s.t < max_seconds:
        # 1. House if needed.
        _maybe_build_house(s)

        # 2. Keep the TC producing villagers (until Castle click is up).
        if s.age_up_in_progress != "castle":
            sim.queue_villager(s)

        # 3. Assign any freshly-produced villagers.
        before_idle = s.villagers["idle"]
        trained_after_start = _assign_new_villagers(s, policy, trained_after_start)
        _ = before_idle  # (kept for clarity; not used)

        total_vils = s.total_villagers

        # 4. Building & age-up triggers.
        if (s.buildings.get("barracks", 0) == 0
                and not any(b.name == "barracks" for b in s.in_progress)
                and total_vils >= policy.build_barracks_at_vils):
            sim.start_building(s, "barracks", "wood")

        if (s.age == "dark"
                and s.age_up_in_progress is None
                and total_vils >= policy.click_feudal_at_vils):
            sim.start_age_up(s, "feudal")

        # Stable and second feudal building can be queued only after Feudal
        # research has started (in the real game you can pre-place them in
        # Castle Age clicks too, but we keep it simple).
        if (s.age == "feudal" or s.age_up_in_progress == "feudal"):
            if (s.buildings.get("stable", 0) == 0
                    and not any(b.name == "stable" for b in s.in_progress)
                    and total_vils >= policy.build_stable_at_vils):
                sim.start_building(s, "stable", "wood")
            second = policy.second_feudal_building
            if (s.buildings.get(second, 0) == 0
                    and not any(b.name == second for b in s.in_progress)
                    and total_vils >= policy.build_second_feudal_at_vils):
                sim.start_building(s, second, "wood")

        if (s.age == "feudal"
                and s.age_up_in_progress is None
                and total_vils >= policy.click_castle_at_vils):
            if not castle_rebalance_done:
                _rebalance_for_castle(s, policy)
                castle_rebalance_done = True
            sim.start_age_up(s, "castle")

        # 5. Check goal.
        if (s.age == "castle"
                and s.buildings.get("barracks", 0) >= 1
                and s.buildings.get("stable", 0) >= 1
                and (s.buildings.get("archery_range", 0) >= 1
                     or s.buildings.get("blacksmith", 0) >= 1)):
            if verbose:
                s.log_event("GOAL REACHED")
            return s

        sim.tick(s)

    s.log_event(f"TIMEOUT at t={s.t}")
    return s


def goal_reached(s: sim.State) -> bool:
    return (s.age == "castle"
            and s.buildings.get("barracks", 0) >= 1
            and s.buildings.get("stable", 0) >= 1
            and (s.buildings.get("archery_range", 0) >= 1
                 or s.buildings.get("blacksmith", 0) >= 1))
