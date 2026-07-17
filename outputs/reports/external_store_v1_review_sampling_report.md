# external_store_v1 阶段 3：人工复核样本冻结报告

## 冻结范围与可重建性

- 输入：`data/external_eval/processed/external_store_v1_candidates.csv`（仅 `candidate_status=accepted`）
- 输入 SHA-256：`27455f086c4526d575f1605bde3a026b32ea28b5fda8b7f43dfb8d54caeee5e0`
- 固定种子：`20260717`
- 算法：先按 `external_candidate_id` 排序；每次候选排序使用
  `SHA-256(seed|用途|candidate_id)`。类别内以最大余数法分配 role，再以最大余数法分配月份。
- 盲化：复核表按独立的 `SHA-256(seed|review-blind|candidate_id)` 排序并分配 `R001`–`R120`。
- 未修改 candidate、rejected、raw、corpus、snippet、RAG/Web、cache 或 embedding；未生成模型回答，也未抽取替补样本。

## 样本结构

| 组别 | 数量 | 说明 |
| --- | ---: | --- |
| representative | 96 | 固定九类配额 |
| role_special | 4 | mixed 2；statistical_sender_rule 且多 inferred sender 2；并集 4 个不同 session |
| parser_anomaly | 12 | invalid only 5；missing only 5；两类同时关联 2 |
| near_threshold | 8 | 六个月各 1 条，另按最小非负 margin 补 2 条 |
| 合计 | 120 | candidate 与 external session 均全局唯一 |

## 96 条 representative 分布

类别配额与实际完全一致：其他 22、物流发货 21、尺码问题 14、商品咨询 11、退货退款 10、质量问题 5、运费 5、换货 4、价格补偿 4。

| 类别 | legacy_keyword | statistical_sender_rule | 合计 |
| --- | ---: | ---: | ---: |
| 其他 | 9 | 13 | 22 |
| 物流发货 | 9 | 12 | 21 |
| 尺码问题 | 7 | 7 | 14 |
| 商品咨询 | 5 | 6 | 11 |
| 退货退款 | 4 | 6 | 10 |
| 质量问题 | 2 | 3 | 5 |
| 运费 | 2 | 3 | 5 |
| 换货 | 1 | 3 | 4 |
| 价格补偿 | 2 | 2 | 4 |
| 合计 | 41 | 55 | 96 |

月份实际分布为月 1–6：17、12、17、18、22、10。按 role 的月份分布分别为：legacy_keyword `7/4/7/10/9/4`，statistical_sender_rule `10/8/10/8/13/6`。这些实际值就是本次可用池比例经最大余数法的配额；没有发生 fallback。

若细分格不足，脚本只会按规定顺序补位：同类别同 role 的其他月份，然后同类别另一 role 的其他月份；每一笔会写入 `fallbacks`。本次记录为空。

## 24 条风险审计分布

- role_special：月份 1/2/4/5 各 1；类别为其他 2、物流发货 1、退货退款 1；method 为 mixed 2、statistical_sender_rule 2。
- parser_anomaly：月份 1/3/4/5/6 为 2/2/3/3/2；method 为 legacy_keyword 3、statistical_sender_rule 9；原因配额严格为 5/5/2。选择时显式优先未覆盖的月份和类别，同分按固定哈希。
- near_threshold：月份 1/2/3/4/5/6 为 2/1/2/1/1/1；均为 statistical_sender_rule。decision_margin 范围为 `0.186159`–`0.195327`。

representative 与风险审计组必须分别报告人工复核结果，**不得合并为单一总体通过率**。发现无效样本时不替换；无效本身即为候选池质量审计结果。

## 校验与隐私

- 全局唯一性：120 个不同 candidate ID、120 个不同 external session ID；各风险子组与 representative 无重叠。
- 可重建性：第二次运行生成的两个文件 SHA-256 与首次完全一致。
- 复核表只包含 `review_id`、脱敏后的 question/answer 和空白人工标注列；不含 sample group、risk reason、role lineage 或 anomaly 信息，且未预填任何人工标签。
- manifest 仅包含允许的 ID、组别、风险原因、月份、类别、role/anomaly lineage 与 margin；不包含 sender、真实店铺名、绝对路径或未脱敏文本。
- 泄漏检查：对 review question/answer 应用 URL、手机号、身份证样式及绝对路径模式检查，并在写入前脱敏；检查结果无命中。输出列名也不含 sender、store 或 path。

## 输出校验

| 被忽略文件 | SHA-256 |
| --- | --- |
| `data/external_eval/review/external_store_v1_review_sample_120.csv` | `f969bd900e5715b3297a643968cba3f4e5ec1445e2956ffdb870316a39af012c` |
| `data/external_eval/review/external_store_v1_review_manifest.csv` | `97f0570bb9445b91657c4b68949490781515cbab83b226a5debceb6986607b9a` |

两个 row-level CSV 均由 `.gitignore` 的 `data/` 规则忽略。受保护输入在运行前后 SHA-256 相同。
