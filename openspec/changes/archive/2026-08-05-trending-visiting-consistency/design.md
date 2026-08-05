# trending-visiting-consistency Design

## Context

实测证据（robinhood `0xcd827...`，2026-08-05）：trending 源告警 payload 记录 `"visiting_count": 4.0`（实时快照，卡上显示），signal_log 显示该 token 此前以 trending 源多次被拦截（loss_cooldown/too_new），最终以 trending 过门开仓——门禁 visiting 来自 trending 载荷（≥ `visiting_min` 200），与卡上 4 相差两个数量级。

机制：`_handle_trending` 传 `need_visiting_from_info=False` → 载荷完整时门禁前不拉 token info → `apply_light_filters` 用载荷 visiting 判定；过门后 `apply_push_snapshot`（实时重拉）无条件覆盖 `cand.visiting_count` → 卡上显示 token_info 值。`signal-filtering` spec「双源 visiting 门槛」固化了 trending 用载荷的口径。

## Goals / Non-Goals

**Goals:**
- trending 门禁 visiting 与 signal 统一走 token info（同源、同缓存、同 fail-closed）
- 卡片显示口径 = 门禁口径（同一数据源），消除 50 倍分叉
- 阈值按新口径 spike 校准

**Non-Goals:**
- 变更推送卡版式 / visiting 展示逻辑
- 立即重设阈值（依赖 spike 数据，后置）
- 移除 `visiting_min_trending` knob（按校准结果再议）

## Decisions

1. **源统一：一行改动**  
   `_handle_trending` → `_enrich_and_process(cand, need_visiting_from_info=True)`。  
   `merge_info_fields(force_visiting=True)` 现有语义（载荷 visiting 被 token info 覆盖）直接适用；`apply_light_filters` 中 `visiting_min_trending` 分支保持（trending 若有该键仍用其阈值，否则回落 `visiting_min`——RH/BSC 当前即回落）。  
   *备选*：门禁不补查、仅卡上改回门禁值（方案 A）——掩盖口径分裂；或调低阈值（方案 C）——无数据盲调。均否决。

2. **成本与延迟**  
   token info 走 300s 缓存：同 token 5 分钟内重复出现零额外请求；新 trending token +1 请求（热门源 120s 轮询、非延迟敏感，1 req/s 配额下可承受）。补查失败路径沿用 `visiting_missing` 拒绝（与 signal 一致）。

3. **阈值校准（spike，后置）**  
   部署后观察：`/rejects` 的 visiting 拦截量（将上升）与 token_info visiting 分布 → 重设 RH/BSC `visiting_min`；sol 的 `visiting_min=350 / visiting_min_trending=250` 同为 token_info 口径后按数据决定是否收敛。校准任务挂在 tasks 第 4 组，不阻塞核心修复。

4. **测试对齐**  
   `test_visiting.py`：`test_trending_visiting_not_overwritten_by_info` / `test_trending_visiting_not_filled_from_info_when_missing` 改为 force_visiting=True 语义（载荷被覆盖 / 缺失不填充保持 None 并拒绝）。`test_pipeline_integration.py` trending visiting 相关断言同步。`test_filters.py` `visiting_min_trending` 用例保留（knob 未移除）。

## Risks / Trade-offs

- [trending 过门变严，部分 token 被 visiting 拦截] → 预期行为（口径真实化）；`/rejects` 可见，运营据 spike 校准阈值
- [新 trending token +1 API 请求] → 缓存 300s + 热门源非延迟敏感；与信号共享限流桶天然排队
- [`visiting_min_trending` 语义陈旧（注释「payload 滞后」）] → 注释随本次更新，数值校准后处理

## Migration Plan

1. pipeline 一行改动 + filters 注释更新 + 测试修订，全量 pytest
2. 部署（`./scripts/deploy_remote.sh`）
3. 观察 1-2 天 `/rejects` visiting 拦截分布与 token_info visiting 采样 → 校准 RH/BSC 阈值 → 更新 yaml + docs/runtime-params.md
4. 若 `visiting_min_trending` 与新口径数据冲突明显，开后续小变更收敛

## Open Questions

- `visiting_min_trending` 校准后是否收敛为单一阈值？（待 spike 数据，可后置决策）
