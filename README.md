# DynamicVC

### Extending VCWorld with Dynamic Evidence for Perturbation Reasoning

[中文说明](README.zh-CN.md) · [Pipeline guide](docs/dynamic_vc_pipeline.md) · [Project narrative / 项目叙事](docs/project_story.zh-CN.md) · [MIT license](LICENSE)

**DynamicVC builds on the VCWorld framework and extends its biological reasoning workflow with model-derived dynamic evidence.** Within VCWorld's query, context, and DE/DIR task structure, DynamicVC integrates a single-cell perturbation predictor, converts its inference trajectories into gene-level **SimContext** and GO/Reactome pathway evidence, and combines this **Dynamic StateContext** with **Static BioContext** for LLM reasoning. The current flow prediction module uses scDFM.

The organizing question is: **How can VCWorld reason over a perturbation using both static biological knowledge and dynamic model evidence?** The framework establishes the query and task; DynamicVC supplies the additional evidence through three stages: **predict the response → contextualize the trajectory → integrate the evidence in VCWorld reasoning**.

![DynamicVC extends the VCWorld framework with flow prediction and dynamic evidence](assets/dynamicvc-overview.svg)

## Framework and component roles

| Role | Component | Place in DynamicVC |
| --- | --- | --- |
| **Framework foundation** | **VCWorld** | Organizes biological queries, static context, evidence integration, and DE/DIR reasoning tasks |
| **Dynamic evidence extension** | **DynamicVC** | Adds FlowTrace, gene-level SimContext, and pathway programs to that framework |
| **Prediction module** | **scDFM** | Supplies the current conditional flow model and generated cellular responses |
| **Task/model integration** | **GeneTak and LLM runners** | Connects task prompts to compatible models through API or local vLLM generation |

This core release contains the dynamic extension and selected integration components. Static KG construction/retrieval and the complete benchmark evaluator remain external integration points.

## Three connected stages

| Stage | Question | Implementation | Main output |
| --- | --- | --- | --- |
| **1. Perturbation prediction** | What expression profiles does the model predict under a perturbation? | scDFM conditional flow training and ODE inference | Predicted expression profiles and optional FlowTrace NPZ files |
| **2. Dynamic evidence construction** | How do generated gene states vary along the flow, and which pathways do they overlap with? | FlowTrace → gene-level SimContext → GO/Reactome enrichment | Gene and pathway evidence in JSONL |
| **3. VCWorld evidence integration and reasoning** | What do dynamic predictions and static biological context support for a query? | VCWorld task prompts + dynamic evidence → API or local vLLM generation | Generated answers, normalized labels, and optional choice scores |

### 1. Predict cellular responses

The scDFM prediction module supplies a dynamic evidence source for the VCWorld-based workflow. It conditions a vector field on control expression, perturbation identity, and gene identities. Its `predict_y` training path learns from noisy-to-target interpolants, with an optional distributional MMD loss. At inference, ODE integration generates expression profiles from an initial noise sample while retaining the control state as a condition.

The original prediction task remains independently usable. DynamicVC adds optional **FlowTrace** export: sampled path states `X_t`, velocities `v_t`, local endpoint estimates `x1_hat`, and final predictions, indexed by perturbation, cell context, and seed.

Entry points: [`run.sh`](run.sh), [`src/script/run.py`](src/script/run.py), [`config/config_flow.py`](config/config_flow.py).

### 2. Construct dynamic biological evidence

**FlowTrace** is the numerical record; **SimContext** is its structured gene-level interpretation. The converter summarizes deviations from the control mean, trajectory direction and pattern, onset along the flow, velocity pattern, sign stability, and uncertainty heuristics. GO/Reactome over-representation analysis adds pathway context separately for saved ODE times and directions.

Together, the gene and pathway records form the **Dynamic StateContext** added to VCWorld's evidence context. Path state and velocity are primary trajectory evidence; endpoint forecasts provide complementary summaries.

Entry points: [`build_simcontext_from_trace.py`](src/script/build_simcontext_from_trace.py), [`enrich_simcontext_programs.py`](src/script/enrich_simcontext_programs.py).

### 3. Integrate evidence in VCWorld reasoning

VCWorld supplies the framework for a query `(perturbation, gene, cell_line)` and its biological reasoning task. Existing task prompts carry **Static BioContext**, such as drug, target, pathway, gene, and cell-line information. DynamicVC's injector adds matching **Dynamic StateContext** within that workflow. GeneTak task/model integration and the included runners connect enriched prompts to a Gemini/OpenAI-compatible API or a compatible local checkpoint through vLLM.

- **DE** asks whether the queried gene is differentially expressed under the perturbation.
- **DIR** asks about the direction of the response.
- **Evidence sufficiency** expresses whether the available evidence supports an answer.

The included runners normalize and score `yes / no / insufficient`; the API runner's optional choice-scoring prompt is DE-specific. Directional prompts can be used for generation, but structured `UP / DOWN / NO CHANGE` parsing and DIR benchmark scoring require a task-specific adapter. See the [task contract](docs/dynamic_vc_pipeline.md#de-and-dir-task-contract).

Entry points: [`inject_simcontext_into_de_prompts_v2.py`](src/script/inject_simcontext_into_de_prompts_v2.py), [`batch_gemini_infer.py`](vcworld/pipeline/batch_gemini_infer.py), [`batch_vllm_infer.py`](VCworld_Data/batch_vllm_infer.py).

## Repository map

```text
DynamicVC/
├── config/config_flow.py            # Model, training, evaluation, and trace settings
├── src/
│   ├── data_process/               # H5AD preparation, splits, and cell samplers
│   ├── models/                     # scDFM prediction module and related components
│   ├── flow_matching/              # Paths, schedulers, solvers, and OT utilities
│   ├── tokenizer/                  # Gene vocabulary and tokenization
│   ├── loss/                       # Metric utilities
│   ├── utils/                      # Checkpoints, preprocessing, and graph utilities
│   └── script/
│       ├── run.py                  # Stage 1: train, predict, and export FlowTrace
│       ├── build_simcontext_from_trace.py
│       ├── enrich_simcontext_programs.py
│       └── inject_simcontext_into_de_prompts_v2.py
├── vcworld/pipeline/batch_gemini_infer.py
├── VCworld_Data/batch_vllm_infer.py
├── tests/                          # Small post-processing smoke tests
├── docs/                           # Workflow, contracts, and project narrative
├── assets/                         # DynamicVC overview and inherited scDFM assets
├── environment.yml                 # Inherited Linux/CUDA training environment
└── run.sh                          # Original Norman additive training example
```

The directory names preserve existing import paths and script entry points. The current model factory selects `model_type=origin`; other inherited model files are not all exposed as runnable configurations.

## Start here

In a Python 3.10+ environment with NumPy and pytest installed, run from the repository root:

```bash
python -m pytest -q tests/test_dynamic_vc_pipeline.py
```

The two smoke tests exercise synthetic trace-to-SimContext conversion and basic enrichment/prompt formatting without a GPU. They do not validate full model inference or biological performance.

Follow the [pipeline guide](docs/dynamic_vc_pipeline.md) for data requirements, training, trace export, enrichment, prompt formatting, and both LLM backends. You can enter at any stage for which you already have the required artifacts.

The training environment is a Linux/CUDA export. Local vLLM inference requires its own compatible model/runtime environment; the training environment does not include vLLM. Datasets, checkpoints, knowledge-graph files, benchmark prompts, and generated results are external artifacts.

## Interpretation and scope

ODE time is a coordinate of the learned generative flow. It is not calibrated experimental time, and model velocity is not an RNA-velocity measurement. SimContext labels and pathway overlaps describe model-derived evidence; their biological relevance and their effect on DE/DIR accuracy require evaluation.

This release supplies prediction, trace interpretation, enrichment, prompt injection, and batch-generation components. Static KG construction/retrieval and a complete DE/DIR benchmark evaluator are external integration points. A joint structured DE/DIR/confidence output contract and calibrated biological confidence scores are not yet implemented.

## Framework foundation and component attribution

**VCWorld is the framework foundation of DynamicVC.** DynamicVC extends that framework with flow-derived Dynamic StateContext and pathway evidence for perturbation reasoning. GeneTak and the LLM runners provide task/model integration within this workflow.

The current prediction module is derived from [scDFM](https://github.com/AI4Science-WestlakeU/scDFM). Its model code, original training example, and assets retain their upstream attribution. The following citation credits that prediction component:

```bibtex
@inproceedings{yu2026scdfm,
  title={sc{DFM}: Distributional Flow Matching Model for Robust Single-Cell Perturbation Prediction},
  author={Chenglei Yu and Chuanrui Wang and Bangyan Liao and Tailin Wu},
  booktitle={The Fourteenth International Conference on Learning Representations},
  year={2026},
  url={https://openreview.net/forum?id=QSGanMEcUV}
}
```

Upstream [data and checkpoint links](docs/dynamic_vc_pipeline.md#upstream-resources) are collected in the pipeline guide. The source retains the [MIT license](LICENSE).
