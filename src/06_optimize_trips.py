"""
Step 6 - Trip frequency optimisation.

Chooses how many trips to run on each line in each hour so that as few
passengers as possible are left without capacity, for a given amount of
operational effort.

Model (a mixed-integer linear programme, solved with HiGHS through SciPy)
------------------------------------------------------------------------
Sets        l in lines, h in service hours
Data        d[l,h]  average passengers entering line l in hour h
            c[l]    passengers one train of line l carries
            b[l,h]  trips in the current timetable
            e[l]    operational effort of one trip
Variables   x[l,h]  trips to run                        (integer)
            s[l,h]  passengers over capacity            (continuous, >= 0)
            v[l,h]  passengers over SEVERE_LOAD capacity (continuous, >= 0)

            s[l,h] >= d[l,h] - TARGET_LOAD * c[l] * x[l,h]
            v[l,h] >= d[l,h] - SEVERE_LOAD * c[l] * x[l,h]
            lower[l,h] <= x[l,h] <= MAX_TRIPS_PER_HOUR

Objective   1. minimise  sum of s[l,h] + SEVERE_WEIGHT * sum of v[l,h]
               Passengers in a severely overloaded hour count extra, so the
               worst hours are relieved first instead of any overloaded hour.
            2. among the best plans, minimise the secondary goal of the scenario

Scenarios
---------
reschedule  Same number of trips per line per day as today, only moved between
            hours. Costs no extra effort. Secondary goal: change as little as possible.
budget      Today's timetable plus at most B extra trips across the whole network.
            Secondary goal: use as little of the budget as possible.
combined    Rescheduling and a budget of B extra trips together.
match day   The budget scenario on a match day: how many extra trips are needed
            once the measured match-day demand is added.

Inputs : results/baseline_load_ratios.csv
         results/match_day_extra_demand.csv
         data/big3_match_schedule.csv
Outputs: results/optimized_timetable.csv
         results/budget_tradeoff.csv
         results/match_day_plan.csv
         results/optimization_summary.json
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix, eye, hstack, vstack

ROOT = Path(__file__).resolve().parent.parent
LOAD_FILE = ROOT / "results" / "baseline_load_ratios.csv"
MATCH_DEMAND_FILE = ROOT / "results" / "match_day_extra_demand.csv"
MATCH_SCHEDULE_FILE = ROOT / "data" / "big3_match_schedule.csv"
TIMETABLE_FILE = ROOT / "results" / "optimized_timetable.csv"
TRADEOFF_FILE = ROOT / "results" / "budget_tradeoff.csv"
MATCH_PLAN_FILE = ROOT / "results" / "match_day_plan.csv"
SUMMARY_FILE = ROOT / "results" / "optimization_summary.json"

TARGET_LOAD = 1.0          # a train may be filled up to its stated capacity
SEVERE_LOAD = 1.5          # beyond 150% of capacity counts as severe crowding
SEVERE_WEIGHT = 1.0        # extra penalty per passenger above the severe level
MAX_TRIPS_PER_HOUR = 30    # 2-minute headway, the practical limit of a metro line
MIN_TRIPS_PER_HOUR = 6     # never worse than a 10-minute headway, unless today already is
BUDGET_STEP = 5
BUDGET_MAX = 150
PLAN_BUDGET = 40           # extra trips per day used for the detailed timetable


def load_problem():
    df = pd.read_csv(LOAD_FILE).sort_values(["hat_adi", "saat"]).reset_index(drop=True)
    df = df.rename(columns={
        "hat_adi": "line", "saat": "hour", "avg_hourly_demand": "demand",
        "sefer_sayisi": "baseline_trips", "standard_capacity_passengers": "capacity",
        "effort_per_extra_trip": "effort",
    })
    df["hour"] = df["hour"].astype(int)
    df["baseline_trips"] = df["baseline_trips"].astype(int)
    return df[["line", "hour", "demand", "baseline_trips", "capacity", "effort"]]


def excess(demand, capacity, trips, level=TARGET_LOAD):
    """Passengers above `level` times capacity for a given timetable."""
    return np.maximum(0.0, demand - level * capacity * trips)


def solve(problem, demand, mode, budget=0.0):
    """
    Solve one scenario. Returns the integer trip plan.

    Variable vector: [x (n), s (n), v (n), t (n)] where t >= |x - b| is only
    used to measure how much a plan differs from today's timetable.
    """
    n = len(problem)
    b = problem["baseline_trips"].to_numpy(float)
    c = problem["capacity"].to_numpy(float)
    e = problem["effort"].to_numpy(float)
    lines = problem["line"].to_numpy()

    upper = np.maximum(MAX_TRIPS_PER_HOUR, b)
    if mode == "budget":
        lower = b.copy()                              # trips can only be added
    else:
        lower = np.minimum(b, MIN_TRIPS_PER_HOUR)     # trips may move, with a service floor

    I = eye(n, format="csr")
    Z = coo_matrix((n, n)).tocsr()
    zeros = np.zeros(n)

    constraints = [
        # capacity:  TARGET_LOAD * c * x + s >= d
        LinearConstraint(hstack([I.multiply(TARGET_LOAD * c[:, None]), I, Z, Z]), demand, np.inf),
        # severe:    SEVERE_LOAD * c * x + v >= d
        LinearConstraint(hstack([I.multiply(SEVERE_LOAD * c[:, None]), Z, I, Z]), demand, np.inf),
        # t >= x - b   and   t >= b - x
        LinearConstraint(hstack([-I, Z, Z, I]), -b, np.inf),
        LinearConstraint(hstack([I, Z, Z, I]), b, np.inf),
    ]

    if mode in ("reschedule", "combined"):
        # Trains cannot move between lines, so each line keeps its own daily total.
        # In "combined" the budget may raise the totals, shared across the network.
        names = pd.unique(lines)
        rows = np.array([np.where(names == l)[0][0] for l in lines])
        per_line = coo_matrix((e, (rows, np.arange(n))), shape=(len(names), n)).tocsr()
        line_totals = per_line @ b
        pad = coo_matrix((len(names), 3 * n)).tocsr()
        if mode == "reschedule":
            constraints.append(LinearConstraint(hstack([per_line, pad]), line_totals, line_totals))
        else:
            constraints.append(LinearConstraint(hstack([per_line, pad]), line_totals, np.inf))

    if mode in ("budget", "combined"):
        total = np.concatenate([e, zeros, zeros, zeros])[None, :]
        constraints.append(LinearConstraint(total, -np.inf, float(e @ b) + budget))

    bounds = Bounds(np.concatenate([lower, zeros, zeros, zeros]), np.concatenate([upper, np.full(3 * n, np.inf)]))
    integrality = np.concatenate([np.ones(n), zeros, zeros, zeros])
    options = {"mip_rel_gap": 0.0}

    # Stage 1: as little crowding as possible, severe crowding weighted extra.
    cost_excess = np.concatenate([zeros, np.ones(n), SEVERE_WEIGHT * np.ones(n), zeros])
    first = milp(cost_excess, constraints=constraints, bounds=bounds, integrality=integrality, options=options)
    if not first.success:
        raise RuntimeError(f"Stage 1 failed ({mode}, budget={budget}): {first.message}")

    # Stage 2: keep that result and optimise the secondary goal.
    keep = LinearConstraint(cost_excess[None, :], -np.inf, first.fun + 1e-6 * max(1.0, first.fun))
    if mode == "reschedule":
        secondary = np.concatenate([zeros, zeros, zeros, np.ones(n)])       # fewest changes
    else:
        secondary = np.concatenate([e, zeros, zeros, 1e-3 * np.ones(n)])    # least effort, then fewest changes
    second = milp(secondary, constraints=constraints + [keep], bounds=bounds,
                  integrality=integrality, options=options)
    result = second if second.success else first
    return np.rint(result.x[:n]).astype(int)


def summarise(problem, demand, trips):
    c = problem["capacity"].to_numpy(float)
    b = problem["baseline_trips"].to_numpy(float)
    over = excess(demand, c, trips)
    load = demand / (c * np.maximum(trips, 1e-9))
    return {
        "passengers_over_capacity": round(float(over.sum()), 1),
        "passengers_over_severe_level": round(float(excess(demand, c, trips, SEVERE_LOAD).sum()), 1),
        "line_hours_over_capacity": int((over > 1e-6).sum()),
        "max_load_ratio": round(float(load.max()), 3),
        "total_trips": int(trips.sum()),
        "extra_trips": int(trips.sum() - b.sum()),
        "trips_changed": int(np.abs(trips - b).sum()),
    }


def match_day_demand(problem, team, kickoff_hour, extra):
    """Normal demand plus the measured extra demand around a match of `team`."""
    demand = problem["demand"].to_numpy(float).copy()
    team_extra = extra[extra["team"] == team]
    lookup = {(r.line, kickoff_hour + int(r.hour_offset)): r.extra_demand for r in team_extra.itertuples()}
    added = np.array([lookup.get((l, h), 0.0) for l, h in zip(problem["line"], problem["hour"])])
    return demand + added, added


def main():
    problem = load_problem()
    demand = problem["demand"].to_numpy(float)
    baseline = problem["baseline_trips"].to_numpy(int)
    capacity = problem["capacity"].to_numpy(float)

    summary = {
        "parameters": {
            "target_load": TARGET_LOAD,
            "severe_load": SEVERE_LOAD,
            "severe_weight": SEVERE_WEIGHT,
            "max_trips_per_hour": MAX_TRIPS_PER_HOUR,
            "min_trips_per_hour": MIN_TRIPS_PER_HOUR,
            "lines": sorted(problem["line"].unique()),
            "line_hours": len(problem),
        },
        "baseline": summarise(problem, demand, baseline),
    }
    base_over = summary["baseline"]["passengers_over_capacity"]
    print(f"Today:      {base_over:>10,.0f} passengers over capacity "
          f"in {summary['baseline']['line_hours_over_capacity']} line-hours")

    # --- Scenario 1: reschedule at zero extra effort -------------------------
    rescheduled = solve(problem, demand, "reschedule")
    summary["reschedule"] = summarise(problem, demand, rescheduled)
    print(f"Reschedule: {summary['reschedule']['passengers_over_capacity']:>10,.0f} "
          f"(moves {summary['reschedule']['trips_changed'] // 2} trips, no extra effort)")

    # --- Scenario 2 and 3: budget of extra trips, with and without rescheduling
    rows, plans = [], {}
    for budget in range(0, BUDGET_MAX + 1, BUDGET_STEP):
        for mode in ("budget", "combined"):
            trips = solve(problem, demand, mode, budget)
            plans[(mode, budget)] = trips
            rows.append({"extra_trip_budget": budget, "scenario": mode, **summarise(problem, demand, trips)})
    tradeoff = pd.DataFrame(rows)
    tradeoff.to_csv(TRADEOFF_FILE, index=False)

    # Some overload cannot be removed at all: the hour would need more trips than the headway limit allows.
    unavoidable = excess(demand, capacity, np.maximum(MAX_TRIPS_PER_HOUR, baseline))
    summary["unavoidable_at_headway_limit"] = {
        "passengers_over_capacity": round(float(unavoidable.sum()), 1),
        "line_hours": [
            {"line": l, "hour": int(h), "passengers_over_capacity": round(float(u), 1)}
            for l, h, u in zip(problem["line"], problem["hour"], unavoidable) if u > 1e-6
        ],
    }
    needed = np.maximum(baseline, np.minimum(MAX_TRIPS_PER_HOUR, np.ceil(demand / (TARGET_LOAD * capacity))))
    summary["extra_trips_to_reach_headway_limit_result"] = int(needed.sum() - baseline.sum())

    plan = plans[("combined", PLAN_BUDGET)]
    summary[f"combined_budget_{PLAN_BUDGET}"] = summarise(problem, demand, plan)
    summary[f"budget_only_{PLAN_BUDGET}"] = summarise(problem, demand, plans[("budget", PLAN_BUDGET)])

    timetable = problem[["line", "hour", "demand", "capacity", "baseline_trips"]].copy()
    timetable["demand"] = timetable["demand"].round(1)
    timetable["baseline_load_ratio"] = (demand / (capacity * baseline)).round(3)
    timetable["rescheduled_trips"] = rescheduled
    timetable["rescheduled_load_ratio"] = (demand / (capacity * rescheduled)).round(3)
    timetable[f"plan_trips_budget_{PLAN_BUDGET}"] = plan
    timetable[f"plan_load_ratio_budget_{PLAN_BUDGET}"] = (demand / (capacity * plan)).round(3)
    timetable.to_csv(TIMETABLE_FILE, index=False)

    # --- Scenario 4: match days ----------------------------------------------
    extra = pd.read_csv(MATCH_DEMAND_FILE, encoding="utf-8-sig")
    schedule = pd.read_csv(MATCH_SCHEDULE_FILE, encoding="utf-8-sig")
    schedule["team"] = schedule["Team"].str.strip().str.lower()
    schedule["kickoff_hour"] = pd.to_datetime(schedule["Time"], format="%H:%M", errors="coerce").dt.hour
    typical_kickoff = schedule.groupby("team")["kickoff_hour"].agg(lambda s: int(s.mode().iloc[0]))

    match_rows = []
    summary["match_day"] = {}
    for team, kickoff in typical_kickoff.items():
        day_demand, added = match_day_demand(problem, team, kickoff, extra)
        before = summarise(problem, day_demand, baseline)
        best = solve(problem, day_demand, "budget", budget=1e6)   # enough budget: find the minimum needed
        after = summarise(problem, day_demand, best)
        summary["match_day"][team] = {
            "typical_kickoff_hour": int(kickoff),
            "extra_passengers_on_modelled_lines": round(float(added.sum()), 1),
            "with_todays_timetable": before,
            "with_optimised_extra_trips": after,
        }
        print(f"Match day ({team}, kick-off {kickoff}:00): {before['passengers_over_capacity']:,.0f} over capacity "
              f"-> {after['passengers_over_capacity']:,.0f} with {after['extra_trips']} extra trips")
        add = best - baseline
        for l, h, a, x in zip(problem["line"], problem["hour"], add, best):
            if a > 0:
                match_rows.append({"team": team, "kickoff_hour": int(kickoff), "line": l, "hour": int(h),
                                   "extra_trips": int(a), "total_trips": int(x)})
    pd.DataFrame(match_rows).to_csv(MATCH_PLAN_FILE, index=False, encoding="utf-8-sig")

    SUMMARY_FILE.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    for mode in ("budget", "combined"):
        t = tradeoff[tradeoff["scenario"] == mode]
        print(f"\n{mode}: extra trips -> passengers over capacity")
        print("  " + "  ".join(f"{int(r.extra_trip_budget)}:{r.passengers_over_capacity:,.0f}" for r in t.itertuples()
                               if r.extra_trip_budget % 20 == 0))
    print(f"\nCannot be removed at a {60 // MAX_TRIPS_PER_HOUR}-minute headway: "
          f"{summary['unavoidable_at_headway_limit']['passengers_over_capacity']:,.0f} passengers "
          f"in {len(summary['unavoidable_at_headway_limit']['line_hours'])} line-hours")
    print(f"Saved -> {TIMETABLE_FILE.name}, {TRADEOFF_FILE.name}, {MATCH_PLAN_FILE.name}, {SUMMARY_FILE.name}")


if __name__ == "__main__":
    main()
