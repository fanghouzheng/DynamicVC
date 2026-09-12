# DynamicVC pipeline guide

DynamicVC is one evidence flow with three independently inspectable stages:

```text
H5AD + perturbation → conditional flow prediction
  → FlowTrace (X_t, v_t, x1_hat, final)
  → SimContext + GO/Reactome programs
  → Dynamic StateContext + Static BioContext
  → VCWorld/GeneTak DE/DIR prompts
  → Gemini or vLLM hypotheses
```

The stages communicate through files, so model output, interpretation, prompt construction, and LLM results can be audited separately.

## 1. Flow prediction and FlowTrace

`src/script/run.py` loads an H5AD dataset through `src/data_process/data.py`, constructs the gene vocabulary and co-expression mask, instantiates the active flow model, and trains or restores a checkpoint. The current factory path is `model_type=origin`. In `predict_y`, the model learns a conditional vector field from a noise-to-target interpolation; ODE inference generates a response conditioned on control expression and perturbation identity.

`run.sh` is the original Norman additive training example. It is a starting point, not a portable one-click experiment: data, checkpoint, device, environment, and split settings must match.

### Data contract

Built-in Norman and ComboSciPlex branches expect their dataset-specific metadata. Generic single-drug data must expose one of `condition`, `drug`, `Drug`, `perturbation`, `treatment`, or `compound`; control cells are detected from `is_control`, `control`, or common control labels. See `Data.process_data()` for exact split and cache behavior.

### Export an inference-time trace

```bash
PYTHONPATH=. python src/script/run.py \
  --test_only --checkpoint_path=/path/to/checkpoint.pt \
  --data_name=norman --model_type=origin \
  --fusion_method=differential_perceiver \
  --perturbation_function=crisper --noise_type=Gaussian \
  --mode=predict_y --eval_every=0 --trace_every=1 \
  --trace_times=0.2,0.5,0.8,1.0 \
  --trace_n_cells=128 --trace_n_seeds=5 --trace_gene_panel=all
```

`--eval_every=0` makes this trace-only. Use `--trace_groupby_obs=cell_name` to separate contexts when that observation exists; an empty value pools controls and targets. The output contains one `seed_*.npz` per perturbation/context with `times`, `gene_names`, control/target summaries, `x_t_mean`, `velocity_mean`, `x1_hat_mean`, `final_mean`, and variance summaries. Cell-level arrays are optional.

Only inference-time states should enter downstream prompts. Training interpolants or target labels would leak the answer. `t` is position along the learned generative flow, not calibrated experimental time.

## 2. SimContext and pathway programs

### Build gene-level SimContext

```bash
python src/script/build_simcontext_from_trace.py \
  --trace-dir=/path/to/test_only/trace \
  --out=/path/to/simcontext.trajectory.jsonl \
  --csv-out=/path/to/simcontext.trajectory.csv \
  --max-genes-per-perturbation=2000 --program-top-k=20
```

The converter groups seeds by perturbation and context, compares `X_t` with the control mean, and writes one row per `(perturbation, cell_line, gene)`.

| Fields | Meaning |
| --- | --- |
| `delta_xt_by_time`, `path_late_delta`, `path_abs_max` | Path-state deviation from control |
| `trajectory_pattern`, `onset`, `velocity_pattern` | Shape and onset heuristics |
| `sign_stability`, `uncertainty`, `n_seeds` | Cross-seed consistency and uncertainty proxies |
| `x1_hat_delta_by_time`, `delta_final` | Secondary local endpoint and final summaries |
| `*_sentence`, `simcontext` | Prompt-ready evidence text |

`x1_hat` is a local endpoint estimate, not an independently measured endpoint. `final` is the integrated model output and may be clipped at zero by the inference path.

### Add GO and Reactome context

The KG directory must contain `go_gsea.json`, `reactome_gsea.json`, and optionally `go_dict.json`:

```bash
python src/script/enrich_simcontext_programs.py \
  --simcontext-jsonl=/path/to/simcontext.trajectory.jsonl \
  --kg-dir=/path/to/kg \
  --out=/path/to/program_enrichment.trajectory.jsonl \
  --prompt-out=/path/to/prompt_ready_simcontext.trajectory.jsonl \
  --fdr-threshold=0.25
```

For each perturbation/context, positive and negative genes are selected at each saved flow position. A hypergeometric over-representation test and Benjamini-Hochberg correction produce pathway rows and prompt-ready records. The background is the genes present in that SimContext group, so changing the gene panel changes the enrichment universe. Fallback overlaps are retained as explicitly non-significant context.

## 3. Prompt injection and DE/DIR reasoning

### Inject dynamic context

```bash
python src/script/inject_simcontext_into_de_prompts_v2.py \
  --prompts=/path/to/DE_or_DIR_prompts.txt \
  --simcontext-jsonl=/path/to/simcontext.trajectory.jsonl \
  --program-enrichment-jsonl=/path/to/program_enrichment.trajectory.jsonl \
  --out=/path/to/prompts_with_dynamic_vc_evidence.txt
```

The injector normalizes drug, gene, and cell-line names, matches each query tuple, and inserts path-state, velocity, endpoint, same drug-cell module, and pathway evidence. Unmatched tuples remain with an explicit no-evidence statement unless `--only-matched` is used.

### DE and DIR task contract

The conceptual output is:

```text
DE: YES / NO / INSUFFICIENT
DIR: UP / DOWN / NO CHANGE
Confidence: LOW / MODERATE / HIGH
```

The current runners normalize generated labels and optionally score A/B/C choices for `yes / no / insufficient`; the choice prompt is DE-specific. They do not yet provide a shared structured parser or calibrated confidence for independent DIR labels. A DIR benchmark should provide a task-specific prompt/parser, retain the raw answer, and report how direction labels were derived.

### Hosted API runner

`vcworld/pipeline/batch_gemini_infer.py` supports resumable concurrent OpenAI-compatible calls, timeouts, retries, JSON/TXT output, and optional choice scoring. Set `GEMINI_API_KEY` or `PROXY_API_KEY`; set `GEMINI_BASE_URL` for a proxy. `--pred-label-source choice` uses A/B/C scoring when available; the default uses the generated answer.

### Local vLLM runner

`VCworld_Data/batch_vllm_infer.py` supports local checkpoints, chat templates, batching, tensor parallelism, resume, and optional choice scoring. vLLM is not included in the training environment. Validate checkpoint files and ensure tensor parallel size divides the model attention-head count.

## Reproducibility and boundaries

```bash
python -m pytest -q tests/test_dynamic_vc_pipeline.py
```

The smoke tests cover post-processing fixtures, not model quality, GPU behavior, API availability, or pathway validity. Keep H5AD files, checkpoints, KG archives, prompts, and generated results outside the source release. Static KG construction/retrieval and benchmark scoring are integration points. Treat Dynamic StateContext as model-derived soft evidence requiring biological validation.

## Upstream resources

- Norman: <https://figshare.com/articles/dataset/Norman_et_al_2019_Science_labeled_Perturb-seq_data/24688110>
- ComboSciPlex: <https://figshare.com/articles/dataset/combosciplex/25062230>
- scDFM source: <https://github.com/AI4Science-WestlakeU/scDFM>
- Dataset mirror: <https://drive.google.com/drive/folders/1cNpYAt9jVWZN82miNZtkP10YeSo7hufL?usp=sharing>
- Checkpoint mirror: <https://drive.google.com/file/d/1ObRTXCt5_H3TIC54A6nOCKycltq88BwX/view?usp=drive_link>
- These datasets and checkpoints are intentionally not vendored here.
