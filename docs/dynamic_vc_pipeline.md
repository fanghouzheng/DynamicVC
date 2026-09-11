# DynamicVC Core Pipeline

This repository contains the reusable implementation behind the DynamicVC
workflow.  It is intentionally split into three stages so that model
inference, pathway interpretation, and language-model evaluation can be run
and audited independently:

```text
single-cell H5AD
  -> scDFM conditional flow model
  -> inference-time ODE trace (X_t, velocity, x1_hat, final)
  -> gene-level SimContext
  -> time-resolved GO/Reactome enrichment
  -> VCWorld / GeneTak DE or DIR prompts
  -> Gemini or vLLM batch inference and evaluation
```

## 1. Flow prediction

The original flow model and data loader remain under `src/`.  The trace
export is optional and does not change the training objective.  Enable it for
test-only inference (or at matching training checkpoints):

```bash
PYTHONPATH=. python src/script/run.py \
  --test_only \
  --checkpoint_path=/path/to/checkpoint.pt \
  --data_name=plate3_p \
  --model_type=origin \
  --fusion_method=differential_perceiver \
  --perturbation_function=drug \
  --noise_type=Gaussian \
  --mode=predict_y \
  --trace_every=1 \
  --trace_groupby_obs=cell_name \
  --trace_times=0.2,0.5,0.8,1.0 \
  --trace_n_cells=128 \
  --trace_n_seeds=5 \
  --trace_gene_panel=all
```

The command writes one `seed_*.npz` per drug/cell-line query.  Each file
contains `X_t`, `velocity`, local endpoint `x1_hat`, the final ODE endpoint,
control summaries, gene names, and the random seed.  Only inference-time
states should be sent to downstream prompts; training interpolants include
the real target and would leak labels.

Relevant implementation:

- `config/config_flow.py`: trace controls and evaluation options.
- `src/script/run.py`: `generate_trace` and `export_flow_trace`.
- `src/data_process/data.py`: single-drug metadata/control detection and
  train/test split handling.

## 2. FlowTrace SimContext and pathway programs

Convert trace files into one JSONL row per `(drug, cell_line, gene)`:

```bash
python src/script/build_simcontext_from_trace.py \
  --trace-dir=/path/to/test_only/trace \
  --out=/path/to/simcontext.trajectory.jsonl \
  --csv-out=/path/to/simcontext.trajectory.csv \
  --max-genes-per-perturbation=2000 \
  --program-top-k=20
```

The converter ranks path-state effects from `X_t - control`, and records
direction, onset, trajectory pattern, velocity pattern, stability, uncertainty
and endpoint summaries.  Path state and velocity are primary evidence;
`x1_hat` and `final` are retained as secondary fields.

Run time-resolved over-representation analysis against the supplied GO and
Reactome gene sets:

```bash
python src/script/enrich_simcontext_programs.py \
  --simcontext-jsonl=/path/to/simcontext.trajectory.jsonl \
  --kg-dir=perturbqa/datasets/kg \
  --out=/path/to/program_enrichment.trajectory.jsonl \
  --prompt-out=/path/to/prompt_ready_simcontext.trajectory.jsonl \
  --fdr-threshold=0.25
```

Enrichment is performed separately for each time point and direction.  The
script uses a hypergeometric test with Benjamini-Hochberg correction and marks
fallback overlaps as non-significant in the generated sentence.  The output
`prompt_ready_simcontext.trajectory.jsonl` is a structured evidence layer; it
does not make a biological validity claim.

## 3. VCWorld / GeneTak DE and DIR inference

Use the prompt injector to merge model evidence into existing VCWorld or
GeneTak prompt text.  The v2 injector also adds pathway program evidence and
keeps unmatched prompts with an explicit no-evidence marker:

```bash
python src/script/inject_simcontext_into_de_prompts_v2.py \
  --prompts=/path/to/DE_or_DIR_prompts.txt \
  --simcontext-jsonl=/path/to/simcontext.trajectory.jsonl \
  --program-enrichment-jsonl=/path/to/program_enrichment.trajectory.jsonl \
  --out=/path/to/prompts_with_dynamic_vc_evidence.txt
```

The downstream runners are kept separate from the biological evidence
construction:

- `vcworld/pipeline/batch_gemini_infer.py` handles resumable Gemini/OpenAI
  compatible API calls and writes JSON/TXT predictions plus choice scores.
- `VCworld_Data/batch_vllm_infer.py` handles local GeneTak/vLLM generation,
  including resume, tensor parallelism, and DE/DIR label scoring.
- `vcworld/data/extract_triples_per_json.py` converts VCWorld JSON outputs to
  evaluation triples.

The prompt contract is intentionally model-aware: every injected block says
that it is scDFM inference-time trajectory evidence, includes the query tuple,
and distinguishes primary path-state/velocity evidence from endpoint forecast.
LLM output is therefore a downstream hypothesis, not a replacement for
cell-level experimental validation.

## Reproducibility and publication boundary

Only source code, configuration, documentation and small test fixtures belong
in the DynamicVC repository.  H5AD datasets, KG archives, checkpoints,
prompt/result dumps and generated figures are local artifacts and are ignored
by `.gitignore`.  Paths in commands above are deliberately placeholders so
that the same code can run on a workstation, cluster, or CI fixture.
