#!/usr/bin/env python3
"""
CVKI Research v2.x - Experiment Comparison CLI
Compares multiple experimental runs and outputs structured comparative tables.
"""

from pathlib import Path
import sys

root_dir = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(root_dir))

from ai.research.comparison import compare_experiments


def main():
    if len(sys.argv) < 2:
        print("Usage: python compare_runs.py <exp_id_1> [exp_id_2] ...")
        print("Example: python compare_runs.py CVR2-CV-001 CVR2-CV-002")
        sys.exit(1)

    exp_ids = sys.argv[1:]
    results = compare_experiments(exp_ids)
    print("\n" + results["markdown_table"] + "\n")


if __name__ == "__main__":
    main()
