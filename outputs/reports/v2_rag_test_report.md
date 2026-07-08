# V2 Mixed Corpus RAG Test Report

- Generated: 2026-07-08 17:10 UTC
- Corpus: 15,688 docs (QA + reviewed snippets)
- LLM mode: mock
- Pass rate: **20/20**

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
