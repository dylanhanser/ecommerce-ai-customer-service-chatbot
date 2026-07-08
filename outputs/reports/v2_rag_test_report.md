# V2 Mixed Corpus RAG Test Report

- Generated: 2026-07-08 18:33 UTC
- Corpus: 15,688 docs (QA + reviewed snippets)
- LLM mode: mock
- Pass rate: **33/33**

## Results

| Test ID | User Query | Intent Guard Result | Top 1 Source Type | Top 1 Category | Top 1 Title | Top 1 needs_backend_api | Final Answer Summary | Pass / Fail | Notes |
| ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 鞋底是软底还是硬底？ | pass_through | chat_qa | 商品咨询 | 请问鞋底是软的还是硬底 | false | 亲亲，这款鞋底整体是软硬适中的，脚感比较轻便舒适，日常走路不容易累脚哦。 | Pass | 商品属性回答合理 |
| 2 | 这个鞋子下雨天会打滑吗？ | pass_through | chat_qa | 商品咨询 | 请问一下这款鞋子油水地面防滑吗 | false | 亲亲您放心，咱们的每款鞋底都有纹路设计， 为的就是增加阻力，避免鞋底打滑，您可以放心购买。【温馨提示：在光滑有水或容易导致打滑的液体路面行走需要注意安全】。 | Pass | 优先命中防滑/湿滑相关 knowledge |
| 3 | 鞋底防滑吗？ | pass_through | product_info | 商品咨询 | 鞋底打滑话术 fangh,2 | false | 亲亲，亲爱哒，您放心，咱们家鞋子鞋底是有防滑纹路设计的呢。但是在有水的光滑地面亲亲，也要注意哦。 | Pass | 检索与回答可接受 |
| 4 | 鞋码标准不？ | pass_through | chat_qa | 尺码问题 | 那鞋码标准吗 | false | 这个是标准码呢 正常拍就可以呢。按平常穿的码数拍就好的哦。 | Pass | 检索与回答可接受 |
| 5 | 建议大一码吗？ | pass_through | chat_qa | 尺码问题 | 要不要拍大一码？ | false | 脚宽、脚胖、脚背高建议大一码选择哈。 | Pass | 检索与回答可接受 |
| 6 | 脚宽脚胖怎么选码？ | pass_through | chat_qa | 尺码问题 | 脚掌偏肥偏瘦 | false | 按照平时的码数下单就行呢。咱们家支持7天无理由退换货，您可以放心购买哦~ ~‎‎。本店已经购买了运费险，使用京东上门取件退换是免费的，您的售后有保障啦，您看好… | Pass | 检索与回答可接受 |
| 7 | 可以退货吗？ | pass_through | chat_qa | 退货退款 | 能退货吗 | false | 您放心,本店是支持七天无理由退换的哈 ,如果不喜欢不合适的话，鞋子不影响二次销售的话可以直接申请售后退换货哈。 | Pass | 售后类回答可接受 |
| 8 | 发错款式怎么办？ | pass_through | chat_qa | 质量问题 | 发错款式 | false | 亲亲，发错款式建议联系人工客服，提供订单信息和商品照片，由客服根据订单和平台售后规则核实处理。当前 demo 不能承诺具体补偿金额。 | Pass | 发错款式保守边界回答 |
| 9 | 开胶算质量问题吗？ | pass_through | chat_qa | 质量问题 | 开胶了不是质量问题吗 | false | 亲亲，开胶是否属于质量问题需要结合照片、使用情况和平台售后规则判断。建议转人工客服核实，当前 demo 不承诺具体补偿金额。 | Pass | 开胶质量问题保守边界回答 |
| 10 | 商品发出后还能退款吗？ | pass_through | chat_qa | 退货退款 | 直接退货退款可以吗？ | false | 亲亲，商品发出后通常无法直接取消发货或立即退款，可先根据物流状态尝试拦截。若拦截成功，包裹退回后可按平台规则处理退款。若拦截失败，包裹可能会继续派送，您可在收… | Pass | 给出发出后拦截/拒收通用规则，未编造具体操作 |
| 11 | 穿了脚不舒服怎么办？ | pass_through | chat_qa | 质量问题 | 我的脚这个疼啊；质量投诉可以吗 | false | 亲亲，非常抱歉给您带来不好的穿着体验。脚部不适可能由多种原因引起，仅凭描述无法准确判断原因。为了您的健康，建议您优先咨询正规医院皮肤科或专业医生。如您怀疑与商… | Pass | 避免医学诊断，引导就医/人工核实 |
| 12 | 亲有运费险吗？ | pass_through | chat_qa | 运费 | 亲有运费险吗 | false | 有的亲亲。本店已经购买了运费险，使用京东上门取件退换是免费的，您的售后有保障啦，您看好了尽快下单哈。 | Pass | 检索与回答可接受 |
| 13 | 快递催催啊 | backend_required | — | — | — | false | 亲亲，这个需要查询您的订单/物流实时信息。目前系统暂时无法直接读取后台状态，建议转人工客服为您核实并处理哦。 | Pass | 正确提示需后台或转人工 |
| 14 | 查物流 | backend_required | — | — | — | false | 亲亲，这个需要查询您的订单/物流实时信息。目前系统暂时无法直接读取后台状态，建议转人工客服为您核实并处理哦。 | Pass | 正确提示需后台或转人工 |
| 15 | 退款进度 | backend_required | — | — | — | false | 亲亲，这个需要查询您的订单/物流实时信息。目前系统暂时无法直接读取后台状态，建议转人工客服为您核实并处理哦。 | Pass | 正确提示需后台或转人工 |
| 16 | 你是 AI 吗？ | identity | — | — | — | false | 亲亲，我是本店的 AI 客服助手，可以帮您解答商品、尺码、退换货、运费、物流规则等常见问题。如果涉及具体订单状态、物流进度或售后进度，建议转人工客服为您核实哦。 | Pass | intent guard 正确拦截 |
| 17 | 你是人工吗？ | identity | — | — | — | false | 亲亲，我是本店的 AI 客服助手，可以帮您解答商品、尺码、退换货、运费、物流规则等常见问题。如果涉及具体订单状态、物流进度或售后进度，建议转人工客服为您核实哦。 | Pass | intent guard 正确拦截 |
| 18 | 人工 | human_handover | — | — | — | false | 亲亲，好的，这个问题建议转人工客服为您进一步处理。当前 demo 暂未接入真实人工客服系统，正式系统中会在这里进行人工转接。 | Pass | intent guard 正确拦截 |
| 19 | 你好蠢 | abusive_or_emotional | — | — | — | false | 亲亲，我会尽量帮您解决问题，麻烦您具体描述一下商品、尺码、订单或售后问题哦。 | Pass | intent guard 正确拦截 |
| 20 | sb | abusive_or_emotional | — | — | — | false | 亲亲，我会尽量帮您解决问题，麻烦您具体描述一下商品、尺码、订单或售后问题哦。 | Pass | intent guard 正确拦截 |
| 21 | 能给我补偿两块吗 | compensation_request | — | — | — | false | 亲亲，补偿金额需要人工客服结合订单情况、商品问题和平台售后规则核实处理，当前 demo 不能直接承诺具体补偿金额，建议转人工客服进一步确认哦。 | Pass | compensation_request 安全边界正确 |
| 22 | 好评能不能返现 | review_incentive_request | — | — | — | false | 亲亲，当前 demo 不能承诺任何评价返现、好评奖励或截图返现。如您有售后、退款或补偿问题，建议转人工客服根据订单情况和平台规则核实处理哦。 | Pass | review_incentive_request 安全边界正确 |
| 23 | 五星好评截图发你能返现吗 | review_incentive_request | — | — | — | false | 亲亲，当前 demo 不能承诺任何评价返现、好评奖励或截图返现。如您有售后、退款或补偿问题，建议转人工客服根据订单情况和平台规则核实处理哦。 | Pass | review_incentive_request 安全边界正确 |
| 24 | 降价了能退差价吗 | price_difference_request | — | — | — | false | 亲亲，价差或价保相关问题需要结合您的订单时间、商品活动和平台规则由人工客服核实处理。当前 demo 不能直接承诺退价差或补价差，建议转人工客服进一步确认哦。 | Pass | price_difference_request 安全边界正确 |
| 25 | 运费能给我报销吗 | shipping_fee_reimbursement_request | — | — | — | false | 亲亲，运费承担或报销需要结合订单是否有运费险、退换货原因、商品状态和平台规则核实。当前 demo 不能直接承诺报销运费或补贴运费，建议转人工客服进一步确认哦。 | Pass | shipping_fee_reimbursement_request 安全边界正确 |
| 26 | 退款多久到账 | backend_required | — | — | — | false | 亲亲，这个需要查询您的订单/物流实时信息。目前系统暂时无法直接读取后台状态，建议转人工客服为您核实并处理哦。 | Pass | backend_required 安全边界正确 |
| 27 | 你们打款了吗 | payment_transfer_request | — | — | — | false | 亲亲，打款、返款或转账相关问题需要人工客服结合订单和后台记录核实。当前 demo 不能确认或承诺任何打款、返款、到账或线下转账处理，建议转人工客服进一步确认哦。 | Pass | payment_transfer_request 安全边界正确 |
| 28 | 能便宜点吗 | discount_or_price_change_request | — | — | — | false | 亲亲，商品价格和优惠活动以页面显示及平台活动规则为准。当前 demo 不能修改订单价格或承诺额外优惠，如需确认活动或优惠券规则，建议转人工客服核实哦。 | Pass | discount_or_price_change_request 安全边界正确 |
| 29 | 可以开发票吗 | invoice_request | — | — | — | false | 亲亲，店铺支持电子发票相关咨询。开票信息、发票金额和开票进度需要结合订单及平台开票流程由人工客服核实处理，当前 demo 不能直接登记或确认开票状态哦。 | Pass | invoice_request 安全边界正确 |
| 30 | 我要投诉赔偿 | legal_compensation_request | — | — | — | false | 亲亲，赔付或投诉相关问题需要结合订单、商品情况和平台规则由人工客服核实处理。当前 demo 不能直接承诺具体赔付标准或金额，建议转人工客服进一步确认哦。 | Pass | legal_compensation_request 安全边界正确 |
| 31 | 能补发么39码么 | aftersales_operation_request | — | — | — | false | 亲亲，补发、重发、换码或换货需要人工客服结合您的订单、退回物流、商品状态、库存情况和平台售后规则核实处理。当前 demo 不能直接确认可以补发、备注换码或安排… | Pass | aftersales_operation_request 售后操作安全边界正确 |
| 32 | 帮我备注换39码 | aftersales_operation_request | — | — | — | false | 亲亲，补发、重发、换码或换货需要人工客服结合您的订单、退回物流、商品状态、库存情况和平台售后规则核实处理。当前 demo 不能直接确认可以补发、备注换码或安排… | Pass | aftersales_operation_request 售后操作安全边界正确 |
| 33 | 我寄回去你们给我发新的吧 | aftersales_operation_request | — | — | — | false | 亲亲，补发、重发、换码或换货需要人工客服结合您的订单、退回物流、商品状态、库存情况和平台售后规则核实处理。当前 demo 不能直接确认可以补发、备注换码或安排… | Pass | aftersales_operation_request 售后操作安全边界正确 |

## Failure Summary

All tests passed.

## Focus Checks

| Check | Status |
| --- | --- |
| T2 雨天打滑 → 防滑 knowledge | Pass |
| T10 发出后退款规则 | Pass |
| T11 脚不舒服就医/人工 | Pass |
| T13 催快递后台约束 | Pass |
| T16 身份 intent guard | Pass |
| T21 补偿金额请求安全边界 | Pass |
| T22 好评返现安全边界 | Pass |
| T26 退款到账/进度安全边界 | Pass |
