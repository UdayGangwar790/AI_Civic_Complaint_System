"""
CVKI Research v2.x - R0 Experiment Result Storage & Artifact Manager
Organizes experiment dossiers under ai/research/experiments/<experiment_id>/
Enforces hypothesis-first documentation and weight reference discipline.
"""

import json
from pathlib import Path
from typing import Any, Optional
import yaml

from ai.research.config import ExperimentConfig
from ai.research.environment import capture_environment
from ai.research.identity import ExperimentIdentity
from ai.research.metrics import EvaluationMetrics


class ExperimentStorage:
    """Manages experiment directory creation, artifact persistence, and report generation."""

    def __init__(self, base_experiments_dir: Path | str | None = None):
        if base_experiments_dir is None:
            self.base_dir = Path(__file__).resolve().parent / "experiments"
        else:
            self.base_dir = Path(base_experiments_dir)

    def get_experiment_dir(self, experiment_id: str) -> Path:
        return self.base_dir / experiment_id

    def initialize_experiment_dossier(
        self,
        identity: ExperimentIdentity,
        config: ExperimentConfig,
    ) -> Path:
        """
        Creates experiment folder and persists initial config, identity, and README skeleton.
        """
        exp_dir = self.get_experiment_dir(identity.experiment_id)
        exp_dir.mkdir(parents=True, exist_ok=True)

        # 1. Save config.yaml
        config.save_yaml(exp_dir / "config.yaml")

        # 2. Save experiment.json
        with open(exp_dir / "experiment.json", "w", encoding="utf-8") as f:
            json.dump(identity.model_dump(), f, indent=2)

        # 3. Capture environment.json
        env_data = capture_environment()
        with open(exp_dir / "environment.json", "w", encoding="utf-8") as f:
            json.dump(env_data, f, indent=2)

        # 4. Write initial README.md
        readme_content = self._render_readme(identity, config, env_data, metrics=None)
        with open(exp_dir / "README.md", "w", encoding="utf-8") as f:
            f.write(readme_content)

        return exp_dir

    def finalize_experiment(
        self,
        experiment_id: str,
        metrics: EvaluationMetrics,
        actual_outcome: str,
        conclusion: str,
        weight_path: Optional[str] = None,
        weight_sha256: Optional[str] = None,
    ) -> None:
        """
        Records final evaluation metrics, updates outcome & conclusion, and regenerates README.md.
        Never embeds binary weights directly into git; records weight_path and weight_sha256.
        """
        exp_dir = self.get_experiment_dir(experiment_id)
        if not exp_dir.exists():
            raise FileNotFoundError(f"Experiment directory '{exp_dir}' does not exist.")

        # 1. Save metrics.json
        with open(exp_dir / "metrics.json", "w", encoding="utf-8") as f:
            json.dump(metrics.model_dump(exclude_none=True), f, indent=2)

        # 2. Update config.yaml with final hypothesis outcomes
        config = ExperimentConfig.from_yaml(exp_dir / "config.yaml")
        config.hypothesis.actual_outcome = actual_outcome
        config.hypothesis.conclusion = conclusion
        if weight_path:
            config.metadata["weight_path"] = weight_path
        if weight_sha256:
            config.metadata["weight_sha256"] = weight_sha256
        config.save_yaml(exp_dir / "config.yaml")

        # 3. Update experiment.json
        with open(exp_dir / "experiment.json", "r", encoding="utf-8") as f:
            ident_data = json.load(f)
        ident_data["metrics"] = metrics.model_dump(exclude_none=True)
        ident_data["status"] = "COMPLETED"
        if weight_path and weight_path not in ident_data["artifact_paths"]:
            ident_data["artifact_paths"].append(f"weight_ref:{weight_path}:{weight_sha256}")
        with open(exp_dir / "experiment.json", "w", encoding="utf-8") as f:
            json.dump(ident_data, f, indent=2)

        # 4. Update README.md
        with open(exp_dir / "environment.json", "r", encoding="utf-8") as f:
            env_data = json.load(f)
        identity = ExperimentIdentity.model_validate(ident_data)
        readme_content = self._render_readme(identity, config, env_data, metrics=metrics)
        with open(exp_dir / "README.md", "w", encoding="utf-8") as f:
            f.write(readme_content)

    def _render_readme(
        self,
        identity: ExperimentIdentity,
        config: ExperimentConfig,
        env_data: dict[str, Any],
        metrics: Optional[EvaluationMetrics],
    ) -> str:
        h = config.hypothesis
        metrics_md = "*(Evaluation pending)*"
        if metrics:
            m_dict = metrics.model_dump(exclude_none=True)
            metrics_rows = "\n".join([f"| **{k}** | {v} |" for k, v in m_dict.items() if not isinstance(v, (dict, list))])
            metrics_md = f"| Metric | Value |\n| :--- | :--- |\n{metrics_rows}"

        return f"""# Experiment Report: {identity.experiment_id}

**Research Version**: {identity.research_version}  
**Status**: {identity.status}  
**Owner**: {identity.owner}  
**Created At**: {identity.created_at}  

---

## 1. Hypothesis-First Framework
- **Research Question**: {h.question}
- **Hypothesis**: {h.hypothesis}
- **Independent Variable**: {h.independent_variable}
- **Dependent Variables**: {", ".join(h.dependent_variables)}
- **Controls**: {", ".join(h.controls)}
- **Expected Outcome**: {h.expected_outcome}
- **Actual Outcome**: {h.actual_outcome}
- **Conclusion**: {h.conclusion}

---

## 2. Experimental Setup
- **Dataset**: `{config.dataset.id}` (v{config.dataset.version})
  - Train: `{config.dataset.train_split}` | Val: `{config.dataset.val_split}` | Test: `{config.dataset.test_split}`
- **Model**: `{config.model.id}` ({config.model.architecture})
- **Random Seed**: `{config.training.seed}`
- **Reproducibility Class**: `{config.evaluation.reproducibility_class}`

---

## 3. Evaluation Results
{metrics_md}

---

## 4. Software & Hardware Environment
- **Python**: {env_data.get("python_version", "unknown")}
- **OS**: {env_data.get("os", "unknown")}
- **CUDA Available**: {env_data.get("cuda_available", "unknown")} (Version: {env_data.get("cuda_version", "unknown")})
- **Git Revision**: `{env_data.get("git_commit", "unknown")}`
"""
