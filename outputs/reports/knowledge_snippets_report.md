# JD Knowledge Snippets V2 Report

## Summary

- 原始解析条数: 482
- accepted 条数: 419
- rejected 条数: 75
- allowed_for_answer=true 数量: 419
- allowed_for_answer=false 数量: 75
- 保守改写进入 accepted 数量: 12

## 各 category 数量

| 名称 | 数量 |
| --- | ---: |
| 质量问题 | 243 |
| 物流发货 | 40 |
| 尺码问题 | 37 |
| 其他 | 28 |
| 商品咨询 | 26 |
| 价格补偿 | 25 |
| 换货 | 11 |
| 退货退款 | 8 |
| 运费 | 1 |

## 各 source_type 数量

| 名称 | 数量 |
| --- | ---: |
| aftersales_rule | 200 |
| shipping_rule | 79 |
| script_template | 77 |
| product_info | 30 |
| backend_rule | 27 |
| policy_rule | 6 |

## 风险类型统计

| 名称 | 数量 |
| --- | ---: |
| 五星好评截图 | 27 |
| 地址/电话 | 19 |
| 具体补偿金额 | 11 |
| meaningless_or_greeting | 5 |
| 后台操作已完成 | 5 |
| 订单号 | 5 |
| 收款码/线下交易 | 5 |
| 手机号 | 1 |
| 评价返现 | 1 |
| 要求修改退货原因 | 1 |
| 邮箱 | 1 |

## 示例 accepted 10 条

| original_key | category | source_type | allowed | content |
| --- | --- | --- | --- | --- |
| baiy,1 | 价格补偿 | script_template | true | 亲亲百亿补贴商品是打折商品是无法加入购物车的呢，喜欢可以直接拍的呢亲亲 |
| baiy,2 | 价格补偿 | script_template | true | 百亿补贴的链接不参与任何满减呢，因为本身就是最低活动价呢 |
| banxing,1 | 尺码问题 | script_template | true | 每个人的脚型和每双鞋的版型都不一样哦 不能保证每个人的尺码都合适的呢 |
| banxing,2 | 尺码问题 | script_template | true | 我们这边只是提供我们这边试穿的信息呢 个人脚型不同的哦 仅供参考哦 |
| banxing,3 | 尺码问题 | script_template | true | 尺码会因人而异的嗷，有的人脚瘦穿正常码的会觉得大了一点，有的人脚宽穿正常码的会觉得小了 我们一般都是按照大部分买家反馈的数据和厂家提供给的数据卖的，一般大部分都是合适的，但是不保... |
| banxing,4 | 尺码问题 | policy_rule | true | 这款是运动鞋尺码正码的呢，但是每个人脚型不同哦，这款大都客户反映是正码的呢，我们都是按自己试穿结果和大都客户建议的呢。具体的是需要您自己选择的呢。您觉得不合适我们也可以给您提供7... |
| banxing,5 | 尺码问题 | product_info | true | 因为每个人脚掌情况不同的呢 有高有宽的 鞋子款式不同也会存在宽和高的情况 无法每个人契合度都完美的，鞋子一般都会越穿越宽松的，您可以调整下鞋带松紧试下看看会不会好一些呢 |
| banxing,6 | 尺码问题 | script_template | true | 亲亲可以废报纸揉成一团,用水弄湿(轻微)再拿一张报纸包上,然后塞进鞋子挤脚的地方 一定要塞紧了哦 撑个几天后就不会了呢 |
| baozhuang,1 | 质量问题 | shipping_rule | true | 这是政府提倡的环保包装，也是为了减少包装垃圾，我们发出去的时候都是包装完整的，有些破了，是因为快递员需要撕掉包装里面的那个面单，他们需要签收，但是鞋子都是完好的，如果鞋子有破损麻... |
| baozhuang,2 | 换货 | backend_rule | true | 涉及补偿、返款、报销运费或差价处理时，需要人工客服结合订单、商品状态和平台规则核实协商，不承诺具体金额。 |

## 示例 rejected 10 条

| original_key | category | source_type | allowed | content |
| --- | --- | --- | --- | --- |
| az,1 | 其他 | script_template | false | 按照这上面的操作呢 |
| b,1 | 其他 | script_template | false | 有什么可以帮您的呢 |
| b,2 | 价格补偿 | risky_script | false | 订单和服务评价5星点下截图 这边可以给您申请补偿 元您看可以吗 |
| baozhuang,2 | 换货 | risky_script | false | 亲，实在抱歉，我们发出去都是完好的，现在快递暴力派件的问题，我们也很头疼，您检查一下鞋子还能正常穿着吗，这边给您申请一下补偿5元，不行的话我们给您换一双的呢，您看可以吗 |
| bc,1 | 价格补偿 | risky_script | false | 订单和服务评价5星点下截图 这边给您申请补偿 元 您看可以吗 |
| bc,2 | 价格补偿 | risky_script | false | 辛苦您提供服务评价和订单点亮五星，无需晒图，我给您的登记打款好吗 |
| bf,1 | 物流发货 | risky_script | false | 考虑到您的购物体验，订单我帮您特殊申请补发一双，预计24小时发出，还希望您订单有空帮忙追加一下好评可以吗？先谢谢您呐#E-s01 |
| bf,4 | 物流发货 | risky_script | false | 实在遗憾亲亲，原订单无法二次补发，考虑到您的购物体验，订单为您申请20元补偿，还望您谅解好吗 |
| bf,2 | 物流发货 | risky_script | false | 亲亲非常抱歉，出现这样的问题我们深感歉意呢，我们也会反馈厂家改进的 ，您订单和服务5星截图这边给您申请补发一双新的呢 您看可以吗 |
| bf,5 | 物流发货 | risky_script | false | 您订单和服务评价5星截图这边给您申请补发一双行吗 |
