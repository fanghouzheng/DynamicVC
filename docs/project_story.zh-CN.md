# DynamicVC 项目叙事与架构说明

## 一句话定位

DynamicVC 把“单细胞扰动后的表达响应预测”组织成一条可追溯的证据链：先用条件 flow model 生成细胞响应，再从生成轨迹中提取动态状态和通路程序，最后将动态证据与静态生物知识结合，支持 VCWorld/GeneTak 的 DE/DIR 下游推理。

```text
预测的表达分布 → 可检查的 ODE 轨迹 → 基因级 Dynamic StateContext
                 → 通路级程序上下文 → 证据注入的 DE/DIR 问题
                 → LLM 生成的可审计假设
```

## 为什么需要三层

单细胞扰动模型擅长回答“表达会怎样变化”，但模型张量本身不适合直接交给生物学推理任务。DynamicVC 将模型能力分成三个责任边界：

1. **预测层负责响应分布。** 接受对照细胞和扰动条件，学习条件向量场，通过 ODE 生成扰动后的表达状态。
2. **证据层负责解释轨迹。** 保存生成过程中的状态、速度和终点，整理为基因级 SimContext，并用 GO/Reactome 将基因变化扩展为通路程序。
3. **推理层负责回答问题。** 把 Static BioContext 和 Dynamic StateContext 放进任务提示词，调用 API 或本地 LLM，保存原始回答、标签和选项分数。

这样可以分别审计：模型是否生成了响应，轨迹是否支持某个动态描述，通路是否来自明确的富集计算，LLM 是否在完整证据下作答。

## 与 overview 图的对应关系

提供的 `overview_final(1).pdf` 展示了 Dynamic StateContext、Static BioContext、Evidence-grounded prompt 和 LLM Reasoning Output。仓库中的 `assets/dynamicvc-overview.svg` 将这套概念映射为三个代码阶段：

| 图中概念 | 仓库实现 | 说明 |
| --- | --- | --- |
| Flow Model / Cell Dynamic Trajectory | `src/script/run.py`、`src/models/` | 从噪声和对照条件生成表达响应 |
| Dynamic StateContext | `build_simcontext_from_trace.py` | `X_t`、`v_t`、`x1_hat`、终点和稳定性 |
| Pathway programs | `enrich_simcontext_programs.py` | 对保存的 flow 状态做 GO/Reactome 富集 |
| Static BioContext | 外部 KG 和原始任务 prompt | 药物、靶点、通路、基因和细胞背景 |
| Evidence-grounded prompt | `inject_simcontext_into_de_prompts_v2.py` | 按查询元组注入动态证据 |
| LLM Reasoning Output | `vcworld/pipeline/`、`VCworld_Data/` | Gemini/OpenAI-compatible API 或本地 vLLM |

图中的 `t` 应理解为生成 flow 的位置。它与实验采样时间不是同一个量；`v_t` 是模型向量场，不是实测 RNA velocity。图中“上调/下调”是动态状态的解释标签，不能替代独立实验验证。

## 三条主线的输入和输出

### 主线一：原始 flow model 单细胞扰动预测

输入是 H5AD 单细胞表达数据、扰动标识和对照状态。数据处理模块负责识别控制细胞、准备训练/测试划分、选择基因和构造掩码；模型模块负责基因编码、表达值编码、扰动条件融合和向量场预测。

输出是常规预测/评估结果，以及可选的 FlowTrace 文件。FlowTrace 按扰动、细胞上下文和 seed 保存多个状态，使第二条主线可以计算跨 seed 的稳定性和不确定性。没有真实 checkpoint 或 H5AD 时，仓库只支持后处理 smoke test，不能声称完成预测实验。

### 主线二：FlowTraceSimContext 与通路富集扩展

这一层把数值轨迹变成证据对象，而不是重新训练模型。转换器计算相对 control 的状态变化、晚期路径变化、峰值、方向、起始位置和速度模式，再写为 JSONL/CSV。

通路脚本以每个药物-细胞上下文的 SimContext 基因集合为背景，按 flow 时刻和方向执行超几何检验，并用 Benjamini-Hochberg 进行多重检验校正。它同时产生可检查的 enrichment 行和可合并到 prompt 的结构化上下文。

### 主线三：VCWorld/GeneTak/LLM 的 DE/DIR 下游推理

注入器以 `(perturbation, gene, cell_line)` 为查询键，把基因轨迹、同药物-细胞模块和通路结果加入原始 prompt。基因级记录缺失时，可以保留药物-细胞层面的程序上下文并明确标注缺失；完全没有匹配证据时写入 no-evidence 说明。

两个 runner 负责批量调用模型、重试、恢复、保存原文和可选的 A/B/C 选择分数。当前公共评分标签是 `yes / no / insufficient`，适用于“是否影响该基因”的 DE 判断。PDF 中的 `DE + DIR + Confidence` 是项目目标接口；独立的 `UP / DOWN / NO CHANGE` 结构化解析、方向校准和 benchmark 评分需要在具体任务中补上。

## 项目介绍中的推荐表述

> DynamicVC 是一个面向单细胞扰动推理的证据构建框架。它以条件 flow model 预测细胞表达响应，以 inference-time ODE trace 保留生成过程中的动态状态，再通过基因级 SimContext 和 GO/Reactome 程序富集形成 Dynamic StateContext。该动态上下文与静态生物知识一起注入 VCWorld/GeneTak 风格的 DE/DIR 提示词，最终由 Gemini 或本地 LLM 生成可追溯的生物学假设。

推荐避免将 ODE 位置称为真实时间、将模型速度称为 RNA velocity，或将 LLM 回答称为实验结论。项目输出是模型衍生证据和下游假设，需要通过真实数据、独立知识和实验验证评估可靠性。

## 代码阅读路径

```text
配置与数据       config/config_flow.py → src/data_process/data.py
预测与轨迹       src/script/run.py → src/models/instantiate_model.py
动态证据         build_simcontext_from_trace.py → enrich_simcontext_programs.py
任务上下文       inject_simcontext_into_de_prompts_v2.py
下游生成         vcworld/pipeline/batch_gemini_infer.py / VCworld_Data/batch_vllm_infer.py
```

从 `tests/test_dynamic_vc_pipeline.py` 开始可以快速理解第二、三层的数据契约；真实训练和 checkpoint 推理从 `run.sh` 与 `src/script/run.py` 开始。完整命令和字段说明见 [`docs/dynamic_vc_pipeline.md`](dynamic_vc_pipeline.md)。
