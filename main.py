"""
AoE2 Build Order Planner - CLI entry point.

Usage:
    python main.py                  # default: 2000-sample search + 200-iter refine
    python main.py --samples 5000   # bigger random search
    python main.py --quick          # tiny search, for smoke-testing
    python main.py --show-log       # print the full per-event log of the best run
"""

import argparse
import time

from aoe2planner import policy, search, sim


def format_time(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


def print_policy(p: policy.Policy) -> None:
    print("Best policy:")
    print(f"  Starting villager split: F{p.start_food} W{p.start_wood} "
          f"G{p.start_gold} S{p.start_stone}")
    plan_preview = " ".join(p.assignments[:20])
    print(f"  Vil assignments (4th onward): {plan_preview} ...")
    print(f"  Build Barracks at {p.build_barracks_at_vils} vils")
    print(f"  Click Feudal     at {p.click_feudal_at_vils} vils")
    print(f"  Build Stable     at {p.build_stable_at_vils} vils")
    print(f"  Build {p.second_feudal_building:13s} at {p.build_second_feudal_at_vils} vils")
    print(f"  Click Castle     at {p.click_castle_at_vils} vils")
    print(f"  Gold villagers for Castle: {p.gold_villagers_for_castle}")
    print(f"  Min wood villagers (early): {p.min_wood_villagers}")


def print_summary(state: sim.State) -> None:
    v = state.villagers
    print(f"\nFinal state @ t={format_time(state.t)} ({state.t}s)")
    print(f"  Age: {state.age}")
    print(f"  Villagers - food:{v['food']} wood:{v['wood']} gold:{v['gold']} "
          f"stone:{v['stone']} build:{v['build']} idle:{v['idle']}  "
          f"(total {state.total_villagers}, pop {state.pop_used}/{state.pop_cap})")
    print(f"  Resources: F{int(state.food)} W{int(state.wood)} "
          f"G{int(state.gold)} S{int(state.stone)}")
    print(f"  Buildings: {dict((k, v) for k, v in state.buildings.items() if v)}")


def print_log(state: sim.State) -> None:
    print("\nEvent log:")
    for t, msg in state.log:
        print(f"  [{format_time(t)}] {msg}")


def print_key_milestones(state: sim.State) -> None:
    print("\nKey milestones:")
    keys = ("barracks completed", "FEUDAL", "stable completed",
            "archery_range completed", "blacksmith completed", "CASTLE",
            "GOAL")
    for t, msg in state.log:
        if any(k in msg for k in keys):
            print(f"  [{format_time(t)}] {msg}")


def main() -> None:
    ap = argparse.ArgumentParser(description="AoE2 Fast Castle BO optimiser")
    ap.add_argument("--samples", type=int, default=2000,
                    help="random policies to try (default 2000)")
    ap.add_argument("--refine", type=int, default=300,
                    help="hill-climb iterations after random search (default 300)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--quick", action="store_true",
                    help="fast smoke test: 200 samples, 50 refines")
    ap.add_argument("--show-log", action="store_true",
                    help="print full event log for the best policy")
    args = ap.parse_args()

    samples = 200 if args.quick else args.samples
    refines = 50 if args.quick else args.refine

    print(f"Random search: {samples} policies (seed={args.seed})...")
    t0 = time.time()
    best_p, best_s, best_score = search.search(samples=samples, seed=args.seed)
    t1 = time.time()
    print(f"  done in {t1-t0:.1f}s  best score: {best_score} "
          f"(t={format_time(best_s.t) if best_score < 10**6 else 'no-goal'})")

    if refines > 0:
        print(f"Local refine: {refines} iterations...")
        t0 = time.time()
        best_p, best_s, best_score = search.local_refine(
            best_p, iterations=refines, seed=args.seed + 1)
        t1 = time.time()
        print(f"  done in {t1-t0:.1f}s  best score: {best_score} "
              f"(t={format_time(best_s.t) if best_score < 10**6 else 'no-goal'})")

    print()
    print_policy(best_p)
    print_summary(best_s)
    print_key_milestones(best_s)
    if args.show_log:
        print_log(best_s)


if __name__ == "__main__":
    main()
