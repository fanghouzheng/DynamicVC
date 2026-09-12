# DynamicVC

### 从单细胞扰动预测到基于轨迹证据的生物学推理

[English](README.md) · [运行指南](docs/dynamic_vc_pipeline.md) · [项目叙事与架构说明](docs/project_story.zh-CN.md) · [MIT 许可](LICENSE)

**DynamicVC 是连接单细胞扰动预测、动态证据构建与 LLM 下游推理的核心研究仓库。** 项目以 scDFM 条件 flow model 为预测基座，将推理轨迹整理为基因级 **SimContext** 和 GO/Reactome 通路证据，再与 VCWorld/GeneTak 风格提示词中的静态生物知识结合，支持 DE/DIR 任务。

整个项目围绕一个问题展开：**如何把模型预测的细胞响应，转换成能够用于回答生物学问题的证据？** 对应的技术主线是：**预测响应 → 构建动态证据 → 融合知识进行推理**。

![DynamicVC 三阶段架构](assets/dynamicvc-overview.svg)

## 三条主线，一套证据流

| 主线 | 回答的问题 | 核心实现 | 输出 |
| --- | --- | --- | --- |
| **1. 单细胞扰动预测** | 给定对照细胞和扰动，模型预测怎样的表达响应？ | scDFM 条件 flow model、训练与 ODE 推理 | 预测表达谱，以及可选的 FlowTrace |
| **2. 动态证据与通路扩展** | 基因状态沿生成轨迹怎样变化，涉及哪些通路？ | FlowTrace → SimContext → GO/Reactome 富集 | 基因级和通路级结构化证据 |
| **3. DE/DIR 下游推理** | 动态预测与静态知识共同支持怎样的判断？ | 提示词注入、API / vLLM 批量生成 | 回答文本、归一化标签和可选的选项分数 |

### 1. 预测层：保留原始 flow model 主线

scDFM 根据对照表达、扰动身份和基因身份学习条件向量场。`predict_y` 训练路径使用噪声到目标表达的插值，并可加入分布层面的 MMD 损失；推理时从初始噪声出发，在对照表达的条件下积分，生成预测表达谱。

这条主线可以独立训练、预测和评估。DynamicVC 在推理入口增加可选的 **FlowTrace** 导出，记录多个 ODE 时刻的状态 `X_t`、速度 `v_t`、局部终点估计 `x1_hat` 和最终预测。

入口：[训练示例](run.sh)、[训练/推理脚本](src/script/run.py)、[配置](config/config_flow.py)。

### 2. 证据层：将 FlowTrace 转换为 SimContext 和通路上下文

FlowTrace 保留数值轨迹，SimContext 将轨迹整理成以 `(perturbation, gene, cell_line)` 为索引的结构化描述，包括相对对照的偏移、变化方向、轨迹模式、沿 flow 的起始位置、速度模式、方向稳定性和不确定性启发式指标。

随后，GO/Reactome 富集按照保存的 ODE 时刻和上/下方向分别执行，将单个基因的变化扩展为通路层面的上下文。**基因级 SimContext + 通路级证据**共同构成下游使用的 **Dynamic StateContext**。

入口：[FlowTrace → SimContext](src/script/build_simcontext_from_trace.py)、[通路富集](src/script/enrich_simcontext_programs.py)。

### 3. 推理层：将动态证据与 Static BioContext 结合

以“某扰动对某细胞系中某基因的影响”为查询单位，现有 VCWorld/GeneTak 风格提示词提供药物、靶点、通路、基因和细胞背景等 **Static BioContext**。注入器补入同一查询对应的 Dynamic StateContext，再通过 Gemini/OpenAI 兼容接口或本地 vLLM 运行兼容模型。

- **DE**：是否发生差异表达。
- **DIR**：响应方向是什么。
- **证据充分性**：现有证据能否支持该判断。

当前两个 runner 的归一化/选项评分体系是 `yes / no / insufficient`，其中 API runner 的评分提示词明确针对 DE。DIR 提示词可用于生成回答；要将结果稳定输出并评估为独立的 `UP / DOWN / NO CHANGE` 类别，还需要任务适配。详见[任务接口说明](docs/dynamic_vc_pipeline.md#de-and-dir-task-contract)。

入口：[提示词注入](src/script/inject_simcontext_into_de_prompts_v2.py)、[API 批量推理](vcworld/pipeline/batch_gemini_infer.py)、[vLLM 批量推理](VCworld_Data/batch_vllm_infer.py)。

## 阅读仓库的顺序

| 阅读目标 | 位置 |
| --- | --- |
| 理解模型如何训练、预测和导出轨迹 | [`src/script/run.py`](src/script/run.py) |
| 理解数据准备、划分和采样 | [`src/data_process/data.py`](src/data_process/data.py) |
| 理解当前使用的模型 | [`src/models/instantiate_model.py`](src/models/instantiate_model.py)、[`src/models/origin/model.py`](src/models/origin/model.py) |
| 理解轨迹如何变成基因证据 | [`build_simcontext_from_trace.py`](src/script/build_simcontext_from_trace.py) |
| 理解基因证据如何变成通路证据 | [`enrich_simcontext_programs.py`](src/script/enrich_simcontext_programs.py) |
| 理解证据如何进入下游任务 | [`inject_simcontext_into_de_prompts_v2.py`](src/script/inject_simcontext_into_de_prompts_v2.py) |
| 理解不同 LLM 的运行与输出 | [`batch_gemini_infer.py`](vcworld/pipeline/batch_gemini_infer.py)、[`batch_vllm_infer.py`](VCworld_Data/batch_vllm_infer.py) |

现有目录和入口继续使用原路径。`src/models/` 包含继承的模型组件，当前工厂函数实际暴露的模型类型是 `origin`。

## 如何开始

在已安装 NumPy、pytest 的 Python 3.10+ 环境中，从仓库根目录运行后处理 smoke tests：

```bash
python -m pytest -q tests/test_dynamic_vc_pipeline.py
```

两个测试覆盖合成轨迹转换、基础富集与提示词格式化，不需要 GPU、真实数据或 API 密钥。模型训练、checkpoint 推理和下游模型运行参见[完整运行指南](docs/dynamic_vc_pipeline.md)。

`environment.yml` 是继承的 Linux/CUDA 训练环境导出；本地 vLLM 需要单独准备兼容环境。H5AD、checkpoint、KG、任务提示词和结果文件由使用者提供，仓库保留可复用源代码。

## 项目定位与实现边界

DynamicVC 的核心组织方式是把预测、轨迹解释和下游推理连成可追溯的证据链。ODE 时间表示生成过程中的位置，速度表示模型向量场，不能直接解释为实验时间或 RNA velocity。SimContext 的标签与通路富集是模型证据，其生物学有效性和下游收益需要实验评估。

仓库已包含预测、轨迹导出、SimContext、富集、提示词注入和批量生成。框架中的静态 KG 构建/检索、完整 DE/DIR benchmark 评估、联合 DE/DIR/confidence 结构化输出属于外部组件或后续适配范围。

## scDFM 基座与来源

预测基座来自 [scDFM](https://github.com/AI4Science-WestlakeU/scDFM)。原始模型、训练示例和相关素材保留上游归属；DynamicVC 的项目叙事围绕该基座上的动态证据与下游推理流程展开。

使用 scDFM 基座时，请保留[英文 README 中的上游引用](README.md#scdfm-foundation-and-attribution)。数据与 checkpoint 链接见[上游资源](docs/dynamic_vc_pipeline.md#upstream-resources)。代码沿用 [MIT 许可](LICENSE)。
