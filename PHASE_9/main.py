"""
main.py

CLI entry point for Phase 9 - Driver Behaviour Analytics.

Usage:
    python main.py --source data/raw/VED_171101_week_sample.csv
    python main.py --source data/raw                     # directory of CSVs
    python main.py --source data/raw --veh-id 8           # print one driver's report

This runs the full pipeline (preprocess -> features -> detection ->
scoring -> profiling) and prints a console summary. It's also useful
as a smoke test before starting the API or dashboard.
"""

import argparse
import json
import sys

from pipeline import pipeline
from utils.exceptions import DriverBehaviorError
from utils.logger import get_logger

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase 9: Driver Behaviour Analytics")
    parser.add_argument(
        "--source", required=True,
        help="Path to a VED CSV file or a directory containing VED_*week.csv files",
    )
    parser.add_argument(
        "--veh-id", type=int, default=None,
        help="If provided, print a detailed report for this driver only",
    )
    parser.add_argument(
        "--use-llm", action="store_true",
        help="Attempt LLM-generated coaching narrative (requires API key in .env)",
    )
    return parser.parse_args()


def print_fleet_summary() -> None:
    df = pipeline.scored_trips_df
    print("\n" + "=" * 60)
    print("PHASE 9 - FLEET SUMMARY")
    print("=" * 60)
    print(f"Total trips analyzed : {len(df)}")
    print(f"Total drivers         : {df['veh_id'].nunique()}")
    print(f"Total distance (km)   : {df['distance_travelled_km'].sum():.1f}")
    print(f"Mean driver score     : {df['driver_score'].mean():.2f}")
    print("\nProfile distribution:")
    for profile, count in df["driver_profile"].value_counts().items():
        print(f"  {profile:<20} {count}")
    print("=" * 60 + "\n")


def print_driver_report(veh_id: int, use_llm: bool) -> None:
    profile = pipeline.get_driver_profile(veh_id)
    score = pipeline.get_driver_score(veh_id)
    stats = pipeline.get_driver_statistics(veh_id)
    coaching = pipeline.get_driver_coaching(veh_id, use_llm=use_llm)

    print("\n" + "=" * 60)
    print(f"DRIVER REPORT — Vehicle ID {veh_id}")
    print("=" * 60)
    print(f"Overall score : {score}")
    print(f"Profile       : {profile['profile']}")
    print(json.dumps(stats, indent=2, default=str))
    print("\nCoaching recommendations:")
    for card in coaching["cards"]:
        print(f"  [{card['priority'].upper():<6}] {card['message']}")
    if coaching.get("narrative"):
        print("\nLLM narrative:")
        print(coaching["narrative"])
    print("=" * 60 + "\n")


def main() -> int:
    args = parse_args()
    try:
        pipeline.run(args.source)
    except DriverBehaviorError as exc:
        logger.error("Pipeline failed: %s", exc)
        return 1

    print_fleet_summary()

    if args.veh_id is not None:
        try:
            print_driver_report(args.veh_id, args.use_llm)
        except DriverBehaviorError as exc:
            logger.error("Could not generate report for veh_id=%s: %s", args.veh_id, exc)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
