"""
CVKI Research v2.x - R0 Experiment Comparison Framework
Compares experimental runs across models, datasets, metrics, and seeds.
Strictly reports factual measurements without automatically declaring a winner.
"""

import json
from pathlib import Path
from typing import Any, Optional


def load_experiment_metrics(experiment_dir: Path | str) -> dict[str, Any]:
    """Loads metrics.json and config.yaml from an experiment directory."""
    p = Path(experiment_dir)
    data: dict[str, Any] = {}
    
    # Load experiment.json or config.yaml
    exp_json = p / "experiment.json"
    if exp_json.exists():
        with open(exp_json, "r", encoding="utf-8") as f:
            data.update(json.load(f))
            
    metrics_json = p / "metrics.json"
    if metrics_json.exists():
        with open(metrics_json, "r", encoding="utf-8") as f:
            data["evaluated_metrics"] = json.load(f)
    else:
        data["evaluated_metrics"] = data.get("metrics", {})

    return data


def compare_experiments(
    experiment_dirs_or_ids: list[str | Path],
    base_dir: Path | str | None = None,
) -> dict[str, Any]:
    """
    Compares experiments and returns a structured comparison dictionary and formatted markdown table.
    Input: list of experiment IDs (e.g. ['CVR2-CV-001', 'CVR2-CV-002']) or directory paths.
    """
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent / "experiments"
    else:
        base_dir = Path(base_dir)

    rows = []
    for item in experiment_dirs_or_ids:
        path = Path(item) if Path(item).is_dir() else base_dir / str(item)
        if not path.exists():
            rows.append({
                "experiment_id": str(item),
                "model": "unknown",
                "dataset": "unknown",
                "seed": "unknown",
                "precision": "N/A",
                "recall": "N/A",
                "mAP50": "N/A",
                "mAP50_95": "N/A",
                "latency_ms": "N/A",
                "notes": "Experiment directory not found",
            })
            continue

        exp_data = load_experiment_metrics(path)
        metrics = exp_data.get("evaluated_metrics", {})
        
        rows.append({
            "experiment_id": exp_data.get("experiment_id", path.name),
            "model": exp_data.get("model_id", "unknown"),
            "dataset": exp_data.get("dataset_id", "unknown"),
            "seed": exp_data.get("random_seed", "unknown"),
            "precision": metrics.get("precision", "N/A"),
            "recall": metrics.get("recall", "N/A"),
            "mAP50": metrics.get("mAP50", "N/A"),
            "mAP50_95": metrics.get("mAP50_95", "N/A"),
            "latency_ms": metrics.get("inference_latency_ms", "N/A"),
            "notes": exp_data.get("notes", ""),
        })

    # Render markdown table
    header = "| Experiment | Model | Dataset | Seed | Precision | Recall | mAP50 | mAP50-95 | Latency (ms) | Notes |"
    divider = "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
    md_rows = [header, divider]
    for r in rows:
        md_rows.append(
            f"| {r['experiment_id']} | {r['model']} | {r['dataset']} | {r['seed']} | "
            f"{r['precision']} | {r['recall']} | {r['mAP50']} | {r['mAP50_95']} | "
            f"{r['latency_ms']} | {r['notes']} |"
        )
    markdown_table = "\n".join(md_rows)

    return {
        "experiments_count": len(rows),
        "rows": rows,
        "markdown_table": markdown_table,
    }
