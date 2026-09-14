# A-172：VCWorld 对齐后的横向 benchmark

本表对应 A-172 细胞系，比较粒度统一为 VCWorld 的单条
`(cell line, drug, gene)` 二分类 DE 问题。所有方法均在相同的 11,910 个
VCWorld–Tahoe common keys 上评估。

| 方法 | 评估 keys | Truth yes | Truth no | Predicted yes | Insufficient | Coverage | Accuracy | Precision (yes) | Recall (yes) | F1 (yes) | Macro-F1 | AUROC | AUPRC |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| VCWorld Original | 11,910 | 7,304 | 4,606 | 5,587 | 744 | 100.00% | 0.5231 | 0.6784 | 0.5189 | 0.5880 | 0.5510 | 0.6309 | 0.7371 |
| VCWorld Half-Sim | 11,910 | 7,304 | 4,606 | 5,035 | 1,014 | 100.00% | **0.6212** | **0.8318** | 0.5734 | **0.6788** | **0.6668** | **0.7371** | **0.8238** |
| STATE | 11,910 | 7,304 | 4,606 | 3,684 | 0 | 100.00% | 0.5689 | 0.7945 | 0.4007 | 0.5328 | 0.5663 | 0.7111 | 0.7488 |
| CellFlow | 11,910 | 7,304 | 4,606 | 9,331 | 0 | 100.00% | 0.4933 | 0.5680 | **0.7256** | 0.6372 | 0.3986 | 0.2178 | 0.4480 |
| X-Cell | 11,910 | 7,304 | 4,606 | 5,654 | 0 | 100.00% | 0.5913 | 0.7154 | 0.5538 | 0.6243 | 0.5881 | 0.6191 | 0.6186 |

## 说明

- `Truth yes/no` 是 VCWorld DE ground-truth 标签，不是模型预测标签。
- VCWorld 的 `Insufficient` 保留为弃答，并按错误计入 Accuracy；弃答率另行保留在原始 CSV 中。
- 对 STATE、CellFlow、X-Cell，baseline 的二分类 DE 预测定义为保存的 real-vs-control `FDR < 0.05`；AUROC/AUPRC 使用 `-log10(FDR)` 作为连续分数。
- `Coverage` 是相对于本表共同 key 集的覆盖率。由于表格已经限制到共同交集，五个方法均为 100%。VCWorld 原始全集及交集覆盖率见 [`alignment_audit.csv`](alignment_audit.csv)。
- 完整数值见 [`A-172_C32_vcworld_aligned_metrics.csv`](A-172_C32_vcworld_aligned_metrics.csv)。对应图见 [`A-172_C32_vcworld_aligned_core_metrics.png`](A-172_C32_vcworld_aligned_core_metrics.png) 和 [`A-172_C32_vcworld_aligned_metrics.png`](A-172_C32_vcworld_aligned_metrics.png)。

## 简要结论

- VCWorld Half-Sim 在 A-172 上的 Accuracy、Precision、F1、Macro-F1、AUROC 和 AUPRC 均高于 VCWorld Original。
- STATE 的 AUROC/AUPRC 接近 Half-Sim，但 Recall 较低，预测阳性比例明显偏低。
- CellFlow 的 Recall 较高，但预测阳性比例达到 78.35%，同时 AUROC 仅为 0.2178，说明存在明显的阳性偏置。
- X-Cell 的 Accuracy 为 0.5913，低于 Half-Sim 但高于 Original、STATE 和 CellFlow；其 Macro-F1 为 0.5881。
