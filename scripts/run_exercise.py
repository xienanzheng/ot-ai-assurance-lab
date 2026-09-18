#!/usr/bin/env python3
"""Run a fresh LOCAL exercise and save evidence. Uses only Python's standard library."""
import argparse
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("domain", choices=["water", "nuclear", "grid"])
    parser.add_argument("--scenario", help="Scenario ID (default: normal operation)")
    parser.add_argument("--minutes", type=int, default=90)
    parser.add_argument("--mode", choices=["baseline", "advisory", "shadow", "gated_auto"], default="baseline")
    parser.add_argument("--seed", type=int, default=42, help="Water model random seed")
    parser.add_argument("--output", type=Path, default=Path("artifacts/exercises"))
    args = parser.parse_args()
    if not 1 <= args.minutes <= 1440:
        parser.error("--minutes must be between 1 and 1440")
    scenario = args.scenario or {"water": "normal_day", "nuclear": "normal_operation", "grid": "normal_dispatch"}[args.domain]

    def api(path, payload=None, raw=False):
        body = json.dumps(payload).encode() if payload is not None else None
        req = Request("http://127.0.0.1:18780/api/v1" + path, data=body,
                      headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=180) as response:
                data = response.read()
        except HTTPError as exc:
            raise SystemExit(f"Lab API error {exc.code}: {exc.read().decode()}") from exc
        return data if raw else json.loads(data)

    choices = api("/scenarios") if args.domain == "water" else api("/infrastructure/scenarios")[args.domain]
    if scenario not in {s["id"] for s in choices}:
        parser.error("Unknown scenario. Available: " + ", ".join(s["id"] for s in choices))
    # Preserve the preceding in-memory exercise before replacing it.
    args.output.mkdir(parents=True, exist_ok=True)
    preceding = api(f"/training/{args.domain}/export?format=json", raw=True)
    prior_id = json.loads(preceding)["run_id"]
    (args.output / f"{args.domain}-previous-{prior_id}.json").write_bytes(preceding)
    if args.domain == "water":
        config = dict(scenario=scenario, seed=args.seed, duration_hours=24, speed=10, controller_mode=args.mode)
        run_id = api("/runs", config)["id"]
        api(f"/runs/{run_id}/reset", {})
    else:
        api(f"/infrastructure/{args.domain}/command", dict(action="reset", scenario=scenario, controller_mode=args.mode))
    elapsed = 0
    while elapsed < args.minutes:
        chunk = min(1 if args.domain == "water" else 10, args.minutes - elapsed)
        if args.domain == "water":
            api(f"/runs/{run_id}/step", {"minutes": chunk})
        else:
            api(f"/infrastructure/{args.domain}/command", {"action": "step", "minutes": chunk})
        elapsed += chunk
        if elapsed % 10 == 0 or elapsed == args.minutes:
            print(f"{args.domain}: {elapsed}/{args.minutes} simulated minutes", flush=True)
    report = api(f"/training/{args.domain}/export?format=json", raw=True)
    data = json.loads(report)
    stem = f"{args.domain}-{scenario}-{args.mode}-{data['run_id']}"
    (args.output / f"{stem}.json").write_bytes(report)
    (args.output / f"{stem}.csv").write_bytes(api(f"/training/{args.domain}/export?format=csv", raw=True))
    print(json.dumps({"critical_minutes": data["critical_minutes"], **data["metrics"]}, indent=2))
    print(f"Evidence saved to {args.output / stem}.json and .csv; simulation left paused.")


if __name__ == "__main__":
    main()
