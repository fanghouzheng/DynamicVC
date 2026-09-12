# DynamicVC 项目叙事与架构说明

## 一句话定位

**DynamicVC 是以 VCWorld 为底座的动态证据增强框架。** 它围绕 VCWorld 的生物学查询、上下文组织与 DE/DIR 任务，接入单细胞扰动预测模块，从生成轨迹中构建 Dynamic StateContext，与框架中的 Static BioContext 融合后进行推理。scDFM 提供当前的预测模块，GeneTak 与 LLM runners 承接任务/模型接入。

```text
VCWorld 框架：定义查询、组织上下文、设定 DE/DIR 任务
  ├─ Static BioContext：任务提示词中的静态生物知识
  └─ DynamicVC 扩展：scDFM 预测 → FlowTrace → SimContext + 通路富集
                                           → Dynamic StateContext
  两类上下文融合 → VCWorld 任务推理 → GeneTak / LLM 生成回答
```

## 从 VCWorld 的任务出发，加入动态证据

项目的起点是 VCWorld 中的扰动问题：某药物或扰动会怎样影响特定细胞背景中的基因？Static BioContext 提供药物、靶点、通路、基因和细胞背景；DynamicVC 进一步引入模型预测的状态变化，为同一个问题增加动态证据。

因此，VCWorld 的框架角色贯穿查询定义、上下文组织和最终任务推理。三条技术主线描述的是框架内部的证据生产与使用过程：

1. **预测模块负责提供动态证据来源。** 当前接入 scDFM，接受对照细胞和扰动条件，通过条件向量场和 ODE 生成表达响应。
2. **动态证据扩展负责让轨迹可用于框架推理。** 保存状态、速度和终点，整理为基因级 SimContext，并用 GO/Reactome 将基因变化扩展为通路程序。
3. **VCWorld 任务流程负责融合证据并回答问题。** 将 Static BioContext 和 Dynamic StateContext 组织进任务提示词，通过 GeneTak/LLM 接入生成回答，保存原文、标签和选项分数。

这样可以分别审计：模型是否生成了响应，轨迹是否支持某个动态描述，通路是否来自明确的富集计算，LLM 是否在完整证据下作答。

## 与 overview 图的对应关系

参考框架图 `overview_final(1).pdf` 展示了 Dynamic StateContext、Static BioContext、Evidence-grounded prompt 和 LLM Reasoning Output。理解这些模块时，VCWorld 是组织它们的框架底座。仓库总览图 `assets/dynamicvc-overview.svg` 因此采用“VCWorld 外层框架 + 内部三条技术主线”的结构：

| 图中概念 | 仓库实现 | 说明 |
| --- | --- | --- |
| 框架底座：VCWorld | 查询、上下文和任务接口；完整 KG/评估栈外部接入 | 组织整个证据与推理流程 |
| Flow Model / Cell Dynamic Trajectory | `src/script/run.py`、`src/models/` | scDFM 作为预测模块，从噪声和对照条件生成表达响应 |
| Dynamic StateContext | `build_simcontext_from_trace.py` | `X_t`、`v_t`、`x1_hat`、终点和稳定性 |
| Pathway programs | `enrich_simcontext_programs.py` | 对保存的 flow 状态做 GO/Reactome 富集 |
| Static BioContext | VCWorld 任务 prompt 和外部知识组件 | 药物、靶点、通路、基因和细胞背景 |
| Evidence-grounded prompt | `inject_simcontext_into_de_prompts_v2.py` | 在 VCWorld 任务上下文中按查询元组注入动态证据 |
| LLM Reasoning Output | `vcworld/pipeline/`、`VCworld_Data/` | GeneTak/LLM 任务接入，通过 API 或本地 vLLM 生成 |

图中的 `t` 应理解为生成 flow 的位置。它与实验采样时间不是同一个量；`v_t` 是模型向量场，不是实测 RNA velocity。图中“上调/下调”是动态状态的解释标签，不能替代独立实验验证。

## 三条主线的输入和输出

### 主线一：接入原始 flow model 单细胞扰动预测模块

这一模块为 VCWorld 的问题提供响应预测，当前实现来自 scDFM。输入是 H5AD 单细胞表达数据、扰动标识和对照状态。数据处理模块负责识别控制细胞、准备训练/测试划分、选择基因和构造掩码；模型模块负责基因编码、表达值编码、扰动条件融合和向量场预测。

输出是常规预测/评估结果，以及可选的 FlowTrace 文件。FlowTrace 按扰动、细胞上下文和 seed 保存多个状态，使第二条主线可以计算跨 seed 的稳定性和不确定性。没有真实 checkpoint 或 H5AD 时，仓库只支持后处理 smoke test，不能声称完成预测实验。

### 主线二：FlowTraceSimContext 与通路富集扩展

这一层是 DynamicVC 为 VCWorld 增加的动态证据接口：把数值轨迹变成可以与静态上下文共同使用的证据对象。转换器计算相对 control 的状态变化、晚期路径变化、峰值、方向、起始位置和速度模式，再写为 JSONL/CSV。

通路脚本以每个药物-细胞上下文的 SimContext 基因集合为背景，按 flow 时刻和方向执行超几何检验，并用 Benjamini-Hochberg 进行多重检验校正。它同时产生可检查的 enrichment 行和可合并到 prompt 的结构化上下文。

### 主线三：VCWorld 内的证据融合与 GeneTak/LLM DE/DIR 推理

从 VCWorld 的 `(perturbation, gene, cell_line)` 查询出发，注入器把基因轨迹、同药物-细胞模块和通路结果加入框架的原始任务 prompt。基因级记录缺失时，可以保留药物-细胞层面的程序上下文并明确标注缺失；完全没有匹配证据时写入 no-evidence 说明。

两个 runner 负责批量调用模型、重试、恢复、保存原文和可选的 A/B/C 选择分数。当前公共评分标签是 `yes / no / insufficient`，适用于“是否影响该基因”的 DE 判断。PDF 中的 `DE + DIR + Confidence` 是项目目标接口；独立的 `UP / DOWN / NO CHANGE` 结构化解析、方向校准和 benchmark 评分需要在具体任务中补上。

## 项目介绍中的推荐表述

> DynamicVC 是以 VCWorld 为底座的动态证据增强框架，旨在让生物学扰动推理同时利用静态知识与预测的细胞状态变化。项目在 VCWorld 的查询、上下文与 DE/DIR 任务流程中接入单细胞 flow 预测模块，当前采用 scDFM 生成表达响应；通过 inference-time FlowTrace、基因级 SimContext 和 GO/Reactome 富集构建 Dynamic StateContext，与 Static BioContext 共同进入任务提示词，再通过 GeneTak/LLM 接入生成可追溯的生物学假设。

推荐避免将 ODE 位置称为真实时间、将模型速度称为 RNA velocity，或将 LLM 回答称为实验结论。项目输出是模型衍生证据和下游假设，需要通过真实数据、独立知识和实验验证评估可靠性。

## 代码阅读路径

```text
框架与任务       VCWorld 查询、Static BioContext 与 DE/DIR 任务提示词
配置与数据       config/config_flow.py → src/data_process/data.py
预测模块与轨迹   src/script/run.py → src/models/instantiate_model.py（scDFM）
动态证据         build_simcontext_from_trace.py → enrich_simcontext_programs.py
框架内证据融合   inject_simcontext_into_de_prompts_v2.py
下游生成         vcworld/pipeline/batch_gemini_infer.py / VCworld_Data/batch_vllm_infer.py
```

从 `tests/test_dynamic_vc_pipeline.py` 开始可以快速理解第二、三层的数据契约；真实训练和 checkpoint 推理从 `run.sh` 与 `src/script/run.py` 开始。完整命令和字段说明见 [`docs/dynamic_vc_pipeline.md`](dynamic_vc_pipeline.md)。
