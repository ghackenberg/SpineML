from __future__ import annotations

import argparse

from SpineML.benchmark import (
    CONTROLLER_REGISTRY,
    available_examples,
    available_generated_profiles,
    generated_example_names,
    report_rows,
    run_benchmark_suite,
    save_report,
)

# Konfiguration fuer direkten Start ueber den IDE-Play-Button.
# Diese Werte werden verwendet, wenn keine CLI-Argumente uebergeben werden.
DEFAULT_EXAMPLES = ["example-0"]
DEFAULT_CONTROLLERS = ["default", "greedy"]
DEFAULT_SEED_TEXT = "0"
DEFAULT_GENERATED_SCALES = "2"
DEFAULT_GENERATED_INSTANCE_SEEDS = "0"
DEFAULT_TILL = 100.0
DEFAULT_OUTPUT = "benchmark-results.json"


def _parse_int_list(seed_text: str) -> list[int]:
    return [int(part.strip()) for part in seed_text.split(",") if part.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run SpineML controller benchmarks.")
    parser.add_argument(
        "--examples",
        nargs="*",
        default=DEFAULT_EXAMPLES,
        help="Example scripts to benchmark.",
    )
    parser.add_argument(
        "--controllers",
        nargs="*",
        default=DEFAULT_CONTROLLERS,
        choices=sorted(CONTROLLER_REGISTRY.keys()),
        help="Controller variants to benchmark.",
    )
    parser.add_argument(
        "--seeds",
        default=DEFAULT_SEED_TEXT,
        help="Comma-separated controller RNG seeds.",
    )
    parser.add_argument(
        "--generated-profiles",
        nargs="*",
        default=[],
        choices=list(available_generated_profiles()),
        help="Optional generated example profiles to expand into a benchmark matrix.",
    )
    parser.add_argument(
        "--generated-scales",
        default=DEFAULT_GENERATED_SCALES,
        help="Comma-separated scales for generated example matrix.",
    )
    parser.add_argument(
        "--generated-instance-seeds",
        default=DEFAULT_GENERATED_INSTANCE_SEEDS,
        help="Comma-separated instance seeds for generated example matrix.",
    )
    parser.add_argument(
        "--till",
        type=float,
        default=DEFAULT_TILL,
        help="Optional simulation cutoff time.",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help="JSON file for the benchmark report.",
    )
    args = parser.parse_args()

    examples = list(args.examples)
    if args.generated_profiles:
        examples.extend(
            generated_example_names(
                args.generated_profiles,
                _parse_int_list(args.generated_scales),
                _parse_int_list(args.generated_instance_seeds),
            )
        )

    deduplicated_examples: list[str] = []
    seen_examples: set[str] = set()
    for example_name in examples:
        if example_name in seen_examples:
            continue
        seen_examples.add(example_name)
        deduplicated_examples.append(example_name)

    report = run_benchmark_suite(
        examples=deduplicated_examples,
        controllers=args.controllers,
        seeds=_parse_int_list(args.seeds),
        till=args.till,
    )
    save_report(report, args.output)

    print(f"Saved benchmark report to {args.output}")
    for row in report_rows(report):
        print(
            f"{row['example_name']} | {row['controller_name']} | seed={row['seed']} | "
            f"completed_jobs={row['completed_jobs']}/{row['total_jobs']} | "
            f"tardiness={row['total_tardiness']:.3f} | makespan={row['makespan']} | "
            f"throughput={row['throughput_jobs_per_time']:.3f} | "
            f"robot_util={row['robot_utilization']:.3f} | "
            f"machine_util={row['machine_utilization']:.3f} | "
            f"avg_wip={row['average_wip']:.3f} | "
            f"avg_wait={row['average_queue_wait_time']:.3f} | "
            f"max_wait={row['max_queue_wait_time']:.3f} | "
            f"tool_changes={row['tool_change_count']} | "
            f"defects={row['defective_jobs']} | "
            f"queues[start/end/c_main/c_side/m_in/m_out]="
            f"{row['start_queue_length']}/{row['end_queue_length']}/"
            f"{row['corridor_main_queue_length']}/{row['corridor_side_queue_length']}/"
            f"{row['machine_input_queue_length']}/{row['machine_output_queue_length']}"
        )


if __name__ == "__main__":
    main()
