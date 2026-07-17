# external_store_v1 阶段 4：双评审冻结协议

## 设计与保密边界

R1 独立标注全部 120 条；R2 独立标注确定性选择的 24 条。R2 样本为 19 条 representative 与 5 条 risk。两人完成前不得查看对方标签或讨论正式样本；一致性在分歧裁决前计算；裁决结果另存，绝不覆盖两份原始标签。

正式评审文件不得上传到其他 AI 工具或公开网盘，不得转发、搜索原始聊天或查看 R2 manifest。R2 完成后返回文件并删除个人副本。未生成模型回答，也没有开始人工标注。

## 可重建选择

- 种子：`20260717`
- 输入行先由 `external_candidate_id` 稳定排序；同等条件使用 `SHA-256("20260717|secondary|" + external_candidate_id)`。
- representative 按固定类别 4/4/3/2/2/1/1/1/1 分配，再按 primary representative 的 role-method 比例以最大余数法分配，并优先覆盖不同月份。
- risk：role_special 1；invalid_session_end_time only 1；missing_message_content only 1；近阈值 2（优先不同月份，再取最小 margin 与固定哈希）。
- 结果：representative 的 method 为 legacy_keyword 9、statistical_sender_rule 10；所有 fallback 为空。risk 原因为 role_special 1、invalid only 1、missing only 1、closest_to_threshold 2。

## 标注与纳入规则

字段定义、允许值、完全虚构的练习和保密提醒见 `docs/evaluation/external_store_v1_annotation_guide.md`。

只有 `pair_valid=yes`、`question_self_contained=yes`、`answer_relevance=yes`、`role_pairing_correct=yes`、`answer_usable_as_reference=yes`、`residual_pii_found=no`、gold category 非 `invalid` 且 exclude reason 为空的记录，才可进入正式 external test set。任何 `partial` 或 `uncertain` 都进入裁决；发现 residual PII 必须立即隔离且不得纳入。

## 一致性与裁决

24 条按 `review_id` 对齐后，裁决前计算每字段简单一致率和 nominal Cohen's kappa，gold category 按 10 类计算 Cohen's kappa。answer relevance 把 uncertain 视为独立类别计算简单一致率；双方均非 uncertain 时，按 no=0、partial=1、yes=2 计算 weighted kappa。另报告排除 uncertain 后的敏感性分析。

24 条样本量较小，所有这些数字仅作为质量控制证据。聚合报告不得包含 QA 文本；仅包含分歧 `review_id` 的清单写到被忽略文件。裁决应产生独立结果文件，保留 R1/R2 原始标签不变。

## 冻结文件与哈希

| 文件 | SHA-256 |
| --- | --- |
| 原盲化 120 样本 | `f969bd900e5715b3297a643968cba3f4e5ec1445e2956ffdb870316a39af012c` |
| 原 manifest | `97f0570bb9445b91657c4b68949490781515cbab83b226a5debceb6986607b9a` |
| primary review 120 | `f969bd900e5715b3297a643968cba3f4e5ec1445e2956ffdb870316a39af012c` |
| secondary review 24 | `475bbf2c00ca1d43370b47ce1a2f9e5e422b587514cc84edc98b79a894fcb10b` |
| secondary manifest 24 | `e1f11975d8d4d1269573861014aa063f410dba9bfb12ee2607ce87a89a88e531` |

三份 row-level 文件均在 `data/` 下，受 Git ignore 保护。R1/R2 文件只含 `review_id`、脱敏 question/reference answer 与空白人工字段；R2 文件不含组别、风险子类、role lineage、anomaly、月份、candidate ID 或 margin。
