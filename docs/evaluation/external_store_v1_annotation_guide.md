# external_store_v1 人工标注手册

## 工作方式与保密

R1 独立标注全部 120 条；R2 独立标注分配的 24 条。两人完成前不得查看对方标签，也不得讨论正式样本。一致性会在分歧裁决前计算，裁决不会覆盖两份原始标注文件。

R2 不得上传文件到其他 AI 工具或公开网盘，不得转发，不得查看 manifest，不得搜索原始聊天。完成后请返回文件并删除个人副本。

## 字段说明

- `pair_valid`：`yes` 表示问题与回答构成合理、完整的客服 QA；`no` 表示明显错配、空洞或无法构成 QA；`uncertain` 表示无法可靠判断。
- `question_self_contained`：`yes` 表示不依赖缺失前文也能理解主要诉求；`no` 表示必须依赖前文、图片、订单详情或未提供对象；`uncertain` 用于边界情况。
- `answer_relevance`：`yes` 表示直接且充分回应主要问题；`partial` 表示回应了一部分但遗漏关键内容；`no` 表示无关、答非所问或无法解决问题；`uncertain` 表示无法确认。
- `role_pairing_correct`：`yes` 表示用户问题与客服回答方向正确；`no` 表示角色颠倒、错误合并或非客服回答；`uncertain` 表示无法确认。
- `answer_usable_as_reference`：`yes` 表示可作为该问题期望回答意图的人工参考；`no` 表示有明显不安全承诺、强上下文依赖、过时促销、个人订单状态或内容不可用；`uncertain` 表示需要店铺政策才能判断。无需验证店铺政策绝对真实性，也不得上网搜索。
- `residual_pii_found`：只能填 `yes` 或 `no`。包括姓名、电话、地址、订单号、账号或其他可识别信息。备注只能写信息类型，不复制具体内容。
- `gold_category`：只能选其他、物流发货、尺码问题、商品咨询、退货退款、质量问题、运费、换货、价格补偿或 `invalid`；以用户主要诉求为准。
- `exclude_reason`：留空，或选 `empty_or_fragmented_question`、`missing_or_irrelevant_answer`、`wrong_role_pairing`、`context_dependent`、`residual_pii`、`duplicate`、`other`。
- `reviewer_notes`：简短写边界或分歧原因，不复制疑似 PII。

## 冻结纳入规则

仅当以下条件同时满足时，样本才可进入正式 external test set：`pair_valid=yes`、`question_self_contained=yes`、`answer_relevance=yes`、`role_pairing_correct=yes`、`answer_usable_as_reference=yes`、`residual_pii_found=no`、`gold_category` 非 `invalid`，且 `exclude_reason` 为空。

任何 `partial` 或 `uncertain` 都必须进入裁决，不得自动纳入。`residual_pii_found=yes` 必须立即隔离，不能进入正式测试集。

## 完全虚构练习（不计入一致性）

1. 问：`这件蓝色外套有 M 码吗？` 答：`有的，当前 M 码可选。` 解析：pair valid、self-contained、relevance、role pairing、reference 均为 yes；无 PII；类别为尺码问题。
2. 问：`运费怎么计算？` 答：`请查看您昨天那笔订单的专属页面。` 解析：回答相关性可为 partial，但强依赖未提供订单上下文，不能直接作为 reference；应记录 context dependent。
3. 问：`能退货吗？` 答：`您好，请问您需要什么帮助？` 解析：问题完整，但回答没有回应退货；answer relevance 为 no，可记录 missing_or_irrelevant_answer。
4. 问：`这个杯子漏水吗？` 答：`我想换成黑色。` 解析：明显不构成正确问答方向；role pairing 或 pair validity 应为 no。
5. 问：`请联系我处理。` 答：`可以，请在订单页提交售后申请。` 解析：主要对象缺失，问题不自足；按情况记录 question_self_contained=no 与 context dependent。

上述练习均为本手册专门编写，不来自正式候选池，也不模仿真实敏感内容。
