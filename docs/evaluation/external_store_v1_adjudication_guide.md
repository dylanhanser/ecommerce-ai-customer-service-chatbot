# external_store_v1 人工分歧裁决手册

本表仅供人工裁决。两位评审者应讨论达成一致；如不能达成一致，由独立第三人裁决。不得由 AI 作出裁决，也不得用 AI 建议替代人工判断。

每条记录都必须处理，不能只处理影响纳入结果的 7 条。`eligibility_disagreement=yes` 的 7 条应优先讨论，但不改变任何裁决标准。

- 只能填写原本为空的 `<field>_final` 单元格。
- 双方原本一致而已预填的 final 标签是锁定值，不得修改或清空。
- `adjudicator_id` 必填；`adjudication_date` 必须是 `YYYY-MM-DD`；`adjudication_notes` 应简短说明依据。
- notes 不得复制电话号码、地址、账号或其他疑似 PII；仅记录信息类型。
- 标签含义、允许值和冻结纳入规则完全遵循 [标注手册](external_store_v1_annotation_guide.md)。只有所有冻结条件满足且 `exclude_reason` 为空，样本才可纳入；`partial` 和 `uncertain` 不可直接纳入。
- 原始主审和复审标签永久保留，不能覆盖。裁决后标签不得用于重新计算并声称评审者一致性；论文中的一致性指标必须使用裁决前结果。

空白模板的验证结果 `INCOMPLETE  47 DISPUTED FINAL CELLS REQUIRE HUMAN ADJUDICATION` 是预期状态，不是失败。全部人工填写后，运行：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python scripts/validate_external_review_adjudication.py
```
