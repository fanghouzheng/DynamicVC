"""Small dependency-light tests for the DynamicVC post-processing stages."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {relative_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_trace_to_simcontext_smoke(tmp_path: Path) -> None:
    trace = _load_script("build_simcontext", "src/script/build_simcontext_from_trace.py")
    perturbation_dir = tmp_path / "cell_line=A549" / "drug=demo"
    perturbation_dir.mkdir(parents=True)

    genes = np.array(["G1", "G2", "G3", "G4"])
    times = np.array([0.2, 0.8, 1.0], dtype=np.float32)
    source = np.zeros(4, dtype=np.float32)
    for seed in range(2):
        x_t = np.array(
            [[0.2, -0.1, 0.0, 0.0], [0.8, -1.0, 0.1, 0.0], [1.5, -1.5, 0.2, 0.0]],
            dtype=np.float32,
        )
        np.savez(
            perturbation_dir / f"seed_{seed:03d}.npz",
            perturbation=np.array("demo"),
            cell_line=np.array("A549"),
            times=times,
            gene_names=genes,
            source_mean=source,
            source_var=np.ones(4, dtype=np.float32),
            x_t_mean=x_t,
            x1_hat_mean=x_t,
            velocity_mean=np.gradient(x_t, times, axis=0),
            final_mean=x_t[-1],
            final_var=np.ones(4, dtype=np.float32) * 0.1,
        )

    rows = trace.build_rows_for_perturbation(
        str(perturbation_dir),
        effect_quantiles=[0.6, 0.8, 0.95],
        uncertainty_quantiles=[0.33, 0.66],
        effect_threshold_quantile=0.6,
        min_stable_time=0.5,
        max_genes_per_perturbation=0,
        program_top_k=2,
    )

    assert len(rows) == 4
    by_gene = {row["gene"]: row for row in rows}
    assert by_gene["G1"]["path_late_delta"] > 0
    assert by_gene["G2"]["path_late_delta"] < 0
    assert "0.8" in by_gene["G1"]["delta_xt_by_time"]
    assert by_gene["G1"]["trajectory_pattern"] != "flat"


def test_pathway_enrichment_and_prompt_context_smoke(tmp_path: Path) -> None:
    enrich = _load_script("enrich_simcontext", "src/script/enrich_simcontext_programs.py")
    injector = _load_script("inject_simcontext", "src/script/inject_simcontext_into_de_prompts_v2.py")

    rows = [
        {
            "perturbation": "demo",
            "cell_line": "A549",
            "gene": gene,
            "direction": direction,
            "path_effect_size": "large",
            "stability": "stable",
            "trajectory_pattern": "monotonic_increase",
            "velocity_auc_rank_percentile": 0.9,
            "path_abs_rank_percentile": 0.9,
            "path_late_delta": 1.0 if direction == "up" else -1.0,
            "path_abs_max": 1.0,
            "delta_final": 1.0 if direction == "up" else -1.0,
            "sign_stability": 1.0,
            "delta_xt_by_time": {"0.8": 1.0 if direction == "up" else -1.0},
            "velocity_by_time": {"0.8": 1.0 if direction == "up" else -1.0},
            "time_state_labels": {"0.8": "large"},
            "path_state_sentence": "path",
            "velocity_sentence": "velocity",
            "endpoint_forecast_sentence": "endpoint",
            "simcontext": "context",
        }
        for gene, direction in [("G1", "up"), ("G2", "up"), ("G3", "up"), ("G4", "down")]
    ]
    kg_dir = tmp_path / "kg"
    kg_dir.mkdir()
    (kg_dir / "go_gsea.json").write_text(json.dumps({"GO:1": ["G1", "G2", "G3"]}))
    (kg_dir / "reactome_gsea.json").write_text(json.dumps({"R:1": ["G1", "G2", "G3"]}))
    (kg_dir / "go_dict.json").write_text(json.dumps({"GO:1": "demo process"}))

    sets = enrich.load_gene_sets(str(kg_dir))
    hits = enrich.enrich_one_source(
        "demo", "A549", "0.8", "up", {"G1", "G2", "G3"}, "test", {"G1", "G2", "G3", "G4"}, "reactome", sets["reactome"]
    )
    assert hits and hits[0]["overlap"] == 3
    assert "BH-FDR" in hits[0]["program_sentence"]

    formatted = injector.format_simcontext(rows[0], "demo", "G1", "A549", [])
    assert "Model-derived scDFM trajectory evidence" in formatted
    assert "drug=demo" in formatted
