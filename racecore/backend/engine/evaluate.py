"""
Evaluation module for RaceCore.
Contains functions for running batch evaluations and comparing strategies.
"""

from concurrent.futures import ProcessPoolExecutor
from typing import List, Tuple, Dict, Any, Callable
import numpy as np
from simulation import RaceConfig, RaceSimulator, SCENARIO_PRESETS
from .stats import calculate_metrics, bootstrap_difference, calculate_win_rate


def _run_single_strategy(strategy_name: str, strategy_func: Callable,
                        scenario_name: str, base_seed: int, run_idx: int) -> Tuple[str, List]:
    """
    Helper function to run a single strategy simulation.
    Defined at module level to be picklable for ProcessPoolExecutor.
    """
    # Use common random numbers: offset seeds to avoid correlation while maintaining comparability
    seed_for_this_run = base_seed + (run_idx * 100) + hash(strategy_name) % 1000

    # Get scenario config
    if scenario_name not in SCENARIO_PRESETS:
        raise ValueError(f"Unknown scenario: {scenario_name}. Available: {list(SCENARIO_PRESETS.keys())}")

    config_func = SCENARIO_PRESETS[scenario_name]
    config = config_func()
    simulator = RaceSimulator(config, seed_for_this_run)
    lap_records = simulator.simulate_race(strategy_func)
    return strategy_name, lap_records


def run_batch(strategies: List[Tuple[str, Callable]], scenario: str, n: int,
              seed: int = 42, show_progress: bool = True) -> Dict[str, List[List[Any]]]:
    """
    Run a batch of simulations for multiple strategies using common random numbers.

    Args:
        strategies: List of (name, strategy_callable) tuples
        scenario: Scenario preset name
        n: Number of races per strategy
        seed: Base seed (each strategy gets seed + index for common random numbers)
        show_progress: Whether to show progress (simplified for now)

    Returns:
        Dictionary mapping strategy names to lists of LapRecord lists (one per race)
    """
    results = {}

    # Prepare arguments
    args_list = []
    for strategy_name, strategy_func in strategies:
        for i in range(n):
            args_list.append((strategy_name, strategy_func, scenario, seed, i))

    # Execute in parallel
    with ProcessPoolExecutor() as executor:
        futures = [executor.submit(_run_single_strategy, *args) for args in args_list]
        for future in futures:
            strategy_name, lap_records = future.result()
            if strategy_name not in results:
                results[strategy_name] = []
            results[strategy_name].append(lap_records)

    return results


def evaluate_strategies(strategies: List[Tuple[str, Callable]], scenario: str, n: int = 100,
                       seed: int = 42) -> Dict[str, Any]:
    """
    Evaluate multiple strategies against each other and generate a comparison report.

    Args:
        strategies: List of (name, strategy_callable) tuples
        scenario: Scenario preset name
        n: Number of races per strategy
        seed: Base seed for random number generation

    Returns:
        Dictionary containing evaluation results suitable for display or reporting
    """
    # Run the batch simulation
    results = run_batch(strategies, scenario, n, seed)

    # Calculate metrics for each strategy
    strategy_metrics = {}
    strategy_race_times = {}  # Store raw times for pairwise comparisons

    for strategy_name, lap_records_list in results.items():
        metrics = calculate_metrics(lap_records_list)
        strategy_metrics[strategy_name] = metrics

        # Extract race times for comparison
        race_times = []
        for lap_records in lap_records_list:
            total_time = sum(record.lap_time for record in lap_records)
            race_times.append(total_time)
        strategy_race_times[strategy_name] = race_times

    # Generate comparison matrix
    comparison_matrix = {}
    baseline_name = None

    # Find baseline strategy (if present)
    for strategy_name in strategy_metrics.keys():
        if 'baseline' in strategy_name.lower() or strategy_name == 'Baseline':
            baseline_name = strategy_name
            break

    # Compare each strategy against baseline (or first strategy if no baseline)
    reference_strategy = baseline_name if baseline_name else list(strategy_metrics.keys())[0]
    reference_times = strategy_race_times[reference_strategy]

    for strategy_name, race_times in strategy_race_times.items():
        if strategy_name == reference_strategy:
            continue

        mean_diff, ci, significant = bootstrap_difference(race_times, reference_times)
        win_rate = calculate_win_rate(race_times, reference_times)

        comparison_matrix[strategy_name] = {
            'vs_reference': reference_strategy,
            'mean_time_difference': mean_diff,  # positive means this strategy is slower
            'ci_lower': ci[0],
            'ci_upper': ci[1],
            'significant': significant,
            'win_rate_vs_reference': win_rate,
            'mean_race_time': np.mean(race_times),
            'reference_mean_race_time': np.mean(reference_times)
        }

    # Generate scenario by strategy matrix (simplified version)
    scenario_matrix = {}
    for strategy_name in strategy_metrics.keys():
        scenario_matrix[strategy_name] = {
            scenario: strategy_metrics[strategy_name]
        }

    return {
        'scenario': scenario,
        'num_races_per_strategy': n,
        'strategy_metrics': strategy_metrics,
        'strategy_race_times': strategy_race_times,
        'comparison_matrix': comparison_matrix,
        'scenario_matrix': scenario_matrix,
        'reference_strategy': reference_strategy
    }


def print_evaluation_results(results: Dict[str, Any]):
    """
    Print evaluation results in a formatted table.

    Args:
        results: Dictionary returned by evaluate_strategies
    """
    print(f"\nRaceCore Evaluation Results")
    print(f"Scenario: {results['scenario']}")
    print(f"Races per strategy: {results['num_races_per_strategy']}")
    print(f"Reference strategy: {results['reference_strategy']}")
    print("=" * 80)

    # Print strategy metrics
    print("\nStrategy Metrics:")
    print("-" * 80)
    print(f"{'Strategy':<20} {'Mean Time':<12} {'Median Time':<12} {'Std Dev':<10} {'5th %ile':<10} {'95th %ile':<10}")
    print("-" * 80)

    for strategy_name, metrics in results['strategy_metrics'].items():
        print(f"{strategy_name:<20} {metrics.get('mean_race_time', 0):<12.2f} "
              f"{metrics.get('median_race_time', 0):<12.2f} {metrics.get('std_race_time', 0):<10.2f} "
              f"{metrics.get('p5_race_time', 0):<10.2f} {metrics.get('p95_race_time', 0):<10.2f}")

    # Print comparison matrix
    if results['comparison_matrix']:
        print("\nComparison vs Reference Strategy:")
        print("-" * 80)
        print(f"{'Strategy':<20} {'vs Reference':<20} {'Mean Diff (s)':<15} {'95% CI':<20} {'Significant':<12} {'Win Rate':<10}")
        print("-" * 80)

        for strategy_name, comparison in results['comparison_matrix'].items():
            sig_text = "Yes" if comparison['significant'] else "No"
            ci_text = f"[{comparison['ci_lower']:.2f}, {comparison['ci_upper']:.2f}]"
            print(f"{strategy_name:<20} {comparison['vs_reference']:<20} "
                  f"{comparison['mean_time_difference']:<15.2f} {ci_text:<20} {sig_text:<12} "
                  f"{comparison['win_rate_vs_reference']:<10.2%}")


if __name__ == "__main__":
    # Example usage would go here
    pass