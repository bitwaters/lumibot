# trending-visiting-consistency

## Why

实测发现：trending 源过门用 **trending 载荷的 visiting**（≥200 过门），而推送卡显示**实时重拉 token_info 的 visiting**（4）——两个 GMGN 端点同一字段口径相差两个数量级，出现「热度 4 却开仓」的误导卡片。signal 源已强制用 token_info 口径（`force_visiting=True`），trending 是唯一例外，且此例外被 `signal-filtering` spec 固化。

## What Changes

- **trending visiting 统一走 token_info**：`_handle_trending` 改 `need_visiting_from_info=True`，trending 门禁 visiting 强制来自 token info（走 300s 缓存），与 signal 源完全对称；token info 补查失败/无 visiting → fail-closed 拒绝（与 signal 一致）。
- **卡片口径一致**：门禁与推送卡显示同一数据源（token_info），「过门值 vs 卡上值」不再跨端点分叉（缓存 5 分钟内新旧差异远小于 50 倍载荷差）。
- **阈值校准（spike 后置）**：`visiting_min` / `visiting_min_trending` 原本按载荷口径标定（sol 注释「trending payload 可滞后，需更高热度」），统一口径后按 token_info visiting 分布重设 RH/BSC 阈值；`visiting_min_trending` 按校准结果保留或收敛。
- **spec 更新**：`signal-filtering`「双源 visiting 门槛」需求改为两源均走 token info 补查。

## Capabilities

### New Capabilities

- 无

### Modified Capabilities

- `signal-filtering`: 「双源 visiting 门槛」——trending 候选从「使用载荷 visiting」改为「MUST 通过 token info 补查 visiting（与 signal 一致）」，缺失 fail-closed

## Impact

- 代码：`src/lumibot/pipeline.py`（`_handle_trending` 一行：`need_visiting_from_info=True`）；`src/lumibot/filters.py`（`merge_info_fields` force_visiting 注释、`apply_light_filters` 中 `visiting_min_trending` 语义注释更新）
- 行为：**BREAKING（筛选口径）**——trending 门禁变严（按 token_info 真实热度），部分此前靠载荷热度过门的 token 将被 visiting 拦截；落地后 `/rejects` 的 visiting 计数会上升，属预期
- 配置：`config/chains.yaml` RH/BSC `visiting_min` 待 spike 校准（后置任务）
- 测试：`tests/test_visiting.py`（trending 两个用例改 force_visiting 语义）、`tests/test_pipeline_integration.py`（trending visiting 相关断言）、`tests/test_filters.py` 影响检查
- 文档：`docs/runtime-params.md` visiting 行注释；`config/chains.yaml` 注释
