#!/usr/bin/env python3
"""
CLI script for RaceCore evaluation.
Prints a results table comparing strategies across all scenarios.
"""

import argparse
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from engine.evaluate import evaluate_strategies, print_evaluation_results
from simulation import baseline_strategy, get_race_config_always_dry, get_race_config_early_rain
from simulation import get_race_config_late_rain, get_race_config_early_sc, get_race_config_high_deg
from simulation import get_race_config_random_mix, SCENARIO_PRESETS
from simulation import RaceConfig
from simulation import ThresholdStrategy, MonteCarloStrategy


def get_strategies():
    """Get the list of strategies to evaluate"""
    return [
        ("Baseline", baseline_strategy),
        ("Threshold", ThresholdStrategy(RaceConfig())),
        ("MonteCarlo", MonteCarloStrategy(RaceConfig(), num_rollouts=200))
    ]


def main():
    parser = argparse.ArgumentParser(description="RaceCore Strategy Evaluation")
    parser.add_argument("--scenario", choices=list(SCENARIO_PRESETS.keys()) + ["all"],
                        default="all", help="Scenario to evaluate")
    parser.add_argument("--races", type=int, default=50,
                        help="Number of races per strategy (default: 50)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Base seed for random number generation (default: 42)")

    args = parser.parse_args()

    strategies = get_strategies()

    if args.scenario == "all":
        scenarios = list(SCENARIO_PRESETS.keys())
        print(f"Evaluating {len(strategies)} strategies across {len(scenarios)} scenarios")
        print(f"Running {args.races} races per strategy per scenario\n")

        all_results = {}
        for scenario in scenarios:
            print(f"--- Scenario: {scenario} ---")
            results = evaluate_strategies(strategies, scenario, args.races, args.seed)
            all_results[scenario] = results
            print_evaluation_results(results)
            print("\n" + "="*80 + "\n")

    else:
        print(f"Evaluating {len(strategies)} strategies on scenario: {args.scenario}")
        print(f"Running {args.races} races per strategy\n")

        results = evaluate_strategies(strategies, args.scenario, args.races, args.seed)
        print_evaluation_results(results)


if __name__ == "__main__":
    main()