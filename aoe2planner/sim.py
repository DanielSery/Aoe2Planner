"""
Discrete 1-second-tick simulator for an AoE2 build order.

The simulator is intentionally dumb: it advances time, applies gathering
and production, and exposes hooks (`request_*`) that a policy calls each
tick to make decisions. All game-rule validation lives here; all
strategy lives in the policy.
"""

from dataclasses import dataclass, field
from typing import Optional

from . import data


JOBS = ("food", "wood", "gold", "stone")


@dataclass
class InProgressBuilding:
    name: str
    completes_at: int
    builder_return_job: str  # where the builder goes after finishing


@dataclass
class TCQueueItem:
    completes_at: int


@dataclass
class State:
    t: int = 0
    food: float = float(data.START_FOOD)
    wood: float = float(data.START_WOOD)
    gold: float = float(data.START_GOLD)
    stone: float = float(data.START_STONE)

    # Villager assignments. "build" villagers are tied to a specific
    # InProgressBuilding via builders_count below.
    villagers: dict = field(default_factory=lambda: {
        "food": 0, "wood": 0, "gold": 0, "stone": 0, "build": 0, "idle": 0,
    })

    # Completed buildings (count by name).
    buildings: dict = field(default_factory=lambda: {"town_center": 1})
    in_progress: list = field(default_factory=list)  # list[InProgressBuilding]

    tc_queue: list = field(default_factory=list)     # list[TCQueueItem]

    age: str = "dark"  # dark | feudal | castle
    age_up_in_progress: Optional[str] = None         # "feudal" | "castle" | None
    age_up_completes_at: int = -1

    # Track which resources have already paid their dropoff-building cost.
    dropoff_paid: set = field(default_factory=set)

    # Starting scout consumes 1 pop.
    pop_used_extra: int = data.START_SCOUT_POP

    log: list = field(default_factory=list)

    # --- derived ---
    @property
    def pop_used(self) -> int:
        v = self.villagers
        live = v["food"] + v["wood"] + v["gold"] + v["stone"] + v["build"] + v["idle"]
        queued = len(self.tc_queue)
        return live + queued + self.pop_used_extra

    @property
    def pop_cap(self) -> int:
        cap = (self.buildings.get("town_center", 0) * data.TC_POP_PROVIDED
               + self.buildings.get("house", 0) * data.HOUSE_POP_PROVIDED)
        return min(cap, data.POP_MAX)

    @property
    def total_villagers(self) -> int:
        v = self.villagers
        return v["food"] + v["wood"] + v["gold"] + v["stone"] + v["build"] + v["idle"]

    def log_event(self, msg: str) -> None:
        self.log.append((self.t, msg))


def new_state() -> State:
    s = State()
    s.villagers["idle"] = data.START_VILLAGERS
    s.log_event(f"start: {data.START_VILLAGERS} villagers idle, "
                f"resources F{int(s.food)} W{int(s.wood)} G{int(s.gold)} S{int(s.stone)}")
    return s


# ---- mutators called by policy ----

def assign_idle_villager(s: State, job: str) -> bool:
    """Move one idle villager to a gathering job. Pays dropoff cost if first time."""
    if job not in JOBS:
        raise ValueError(f"bad job: {job}")
    if s.villagers["idle"] <= 0:
        return False
    cost = data.DROPOFF_WOOD_COST[job]
    if job not in s.dropoff_paid:
        if s.wood < cost:
            return False
        s.wood -= cost
        s.dropoff_paid.add(job)
        if cost > 0:
            s.log_event(f"dropoff for {job} built (-{cost}W)")
    s.villagers["idle"] -= 1
    s.villagers[job] += 1
    return True


def reassign_villager(s: State, from_job: str, to_job: str) -> bool:
    """Move one villager between gather jobs (no idle-step required)."""
    if from_job not in JOBS or to_job not in JOBS:
        return False
    if s.villagers[from_job] <= 0:
        return False
    if to_job not in s.dropoff_paid:
        cost = data.DROPOFF_WOOD_COST[to_job]
        if s.wood < cost:
            return False
        s.wood -= cost
        s.dropoff_paid.add(to_job)
        if cost > 0:
            s.log_event(f"dropoff for {to_job} built (-{cost}W)")
    s.villagers[from_job] -= 1
    s.villagers[to_job] += 1
    return True


def queue_villager(s: State) -> bool:
    """Queue a villager at the TC if resources, pop room, and queue space allow."""
    if s.food < data.VILLAGER.food:
        return False
    if s.pop_used >= s.pop_cap:
        return False
    # Cap TC queue at a reasonable number (game allows 15 per building).
    if len(s.tc_queue) >= 5:
        return False
    s.food -= data.VILLAGER.food
    # First in queue starts immediately; later ones start after previous finishes.
    if not s.tc_queue:
        start = s.t
    else:
        start = s.tc_queue[-1].completes_at
    s.tc_queue.append(TCQueueItem(completes_at=start + data.VILLAGER.build_time))
    return True


def start_building(s: State, name: str, builder_from_job: str) -> bool:
    """Pull one villager from `builder_from_job` to start a building."""
    bdef = data.BUILDINGS[name]
    if s.food < bdef.food or s.wood < bdef.wood or s.gold < bdef.gold or s.stone < bdef.stone:
        return False
    if s.villagers[builder_from_job] <= 0:
        # try idle as fallback
        if s.villagers["idle"] <= 0:
            return False
        builder_from_job = "idle"
    s.food -= bdef.food
    s.wood -= bdef.wood
    s.gold -= bdef.gold
    s.stone -= bdef.stone
    s.villagers[builder_from_job] -= 1
    s.villagers["build"] += 1
    return_job = builder_from_job if builder_from_job in JOBS else "food"
    s.in_progress.append(InProgressBuilding(
        name=name,
        completes_at=s.t + bdef.build_time,
        builder_return_job=return_job,
    ))
    s.log_event(f"start building {name} (builder from {builder_from_job})")
    return True


def start_age_up(s: State, target_age: str) -> bool:
    """Begin researching Feudal or Castle Age at the TC."""
    if s.age_up_in_progress is not None:
        return False
    if target_age == "feudal":
        if s.age != "dark":
            return False
        if not any(s.buildings.get(b, 0) > 0 for b in data.DARK_AGE_BUILDINGS):
            return False
        tech = data.FEUDAL_AGE
    elif target_age == "castle":
        if s.age != "feudal":
            return False
        feudal_count = sum(s.buildings.get(b, 0) for b in data.FEUDAL_AGE_BUILDINGS)
        if feudal_count < 2:
            return False
        tech = data.CASTLE_AGE
    else:
        raise ValueError(target_age)
    if s.food < tech.food or s.wood < tech.wood or s.gold < tech.gold or s.stone < tech.stone:
        return False
    s.food -= tech.food
    s.wood -= tech.wood
    s.gold -= tech.gold
    s.stone -= tech.stone
    s.age_up_in_progress = target_age
    s.age_up_completes_at = s.t + tech.research_time
    s.log_event(f"start age-up to {target_age} (eta {tech.research_time}s)")
    return True


# ---- per-tick advance ----

def tick(s: State) -> None:
    """Advance the simulation by exactly one second."""
    # Gather resources (production for the second just elapsed).
    s.food += s.villagers["food"] * data.GATHER_RATE["food"]
    s.wood += s.villagers["wood"] * data.GATHER_RATE["wood"]
    s.gold += s.villagers["gold"] * data.GATHER_RATE["gold"]
    s.stone += s.villagers["stone"] * data.GATHER_RATE["stone"]

    s.t += 1

    # TC queue completions.
    completed = [q for q in s.tc_queue if q.completes_at <= s.t]
    for _ in completed:
        s.villagers["idle"] += 1
        s.log_event(f"villager #{s.total_villagers} produced (idle)")
    s.tc_queue = [q for q in s.tc_queue if q.completes_at > s.t]

    # Building completions.
    finished = [b for b in s.in_progress if b.completes_at <= s.t]
    for b in finished:
        s.buildings[b.name] = s.buildings.get(b.name, 0) + 1
        s.villagers["build"] -= 1
        # Builder returns to their previous job (paying no dropoff again).
        if b.builder_return_job in JOBS:
            s.villagers[b.builder_return_job] += 1
        else:
            s.villagers["idle"] += 1
        s.log_event(f"{b.name} completed")
    s.in_progress = [b for b in s.in_progress if b.completes_at > s.t]

    # Age-up completion.
    if s.age_up_in_progress is not None and s.age_up_completes_at <= s.t:
        s.age = s.age_up_in_progress
        s.age_up_in_progress = None
        s.log_event(f"reached {s.age.upper()} AGE")
