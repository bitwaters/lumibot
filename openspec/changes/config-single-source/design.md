# config-single-source Design

## Context

审计结论（2026-08-05）：
- 规则类已全部在 `config/chains.yaml`（strategy/filters/safety/cooldown/execution/sources/global），config.py dataclass 默认值仅是 schema 默认、运行时被 yaml 覆盖，不算多配置源
- 4 处规则类硬编码：`pipeline.py:148` manage 间隔 `5 + uniform(0,2)` s、`pipeline.py:55` `_dual_source_ttl_sec = 30.0`、`pipeline.py:117` trending 预算门槛 `available() < 4`、`telegram_bot.py:55` `ALERTS_PER_CHAIN = 5`
- 可保留的硬编码：429 backoff、重试 sleep(0.25)（限流内部实现细节，主体由 `global.rate_limit` 控制）；卡片文案/URL/标签（展示层）

## Goals / Non-Goals

**Goals:**
- spec 固化「单一配置源」原则，约束后续所有变更
- 3 处规则类硬编码迁入 `global.*`，行为零变化（默认值与现值一致）
- fail-fast 校验强化（pydantic 已天然提供，补充场景级说明）

**Non-Goals:**
- 迁移 429 backoff 等限流内部细节（属实现，非规则）
- 迁移展示层常量（文案/URL/标签）
- 引入运行时热重载

## Decisions

1. **配置字段命名与默认值**（与现硬编码逐一对齐，行为不变）：
   - `global.manage_interval_sec: float = 5.0` → `pipeline._loop_manage` 的 `self._sleep(manage_interval + random.uniform(0, 2))`
   - `global.dual_source_ttl_sec: float = 30.0` → `Pipeline.__init__` 的 `self._dual_source_ttl_sec = app_cfg.global_.dual_source_ttl_sec`
   - `global.alerts_per_chain: int = 5` → `build_dispatcher` 内 `ALERTS_PER_CHAIN` 改从 `app_cfg.global_` 读取
   - `global.trending_defer_budget: float = 4.0` → `pipeline._loop_trending` 的 `available() < budget`（配额低于预算时延后 trending 轮询）
   - 均在 GlobalCfg（config.py:176）新增字段，pydantic 保证 yaml 缺失时用默认值、非法时启动失败
2. **读取路径**：pipeline 已有 `app_cfg`；telegram_bot 的 `build_dispatcher` 已接收 `app_cfg` 参数 ✓ 零签名变更
3. **spec 原则措辞**：规则类（交易/门禁/筛选/安全/采集/限额）强制入 yaml；实现细节与展示层豁免；fail-fast 由 pydantic 模型校验兜底

## Risks / Trade-offs

- [迁移后配置缺失时默认值覆盖真实意图] → 默认值与现硬编码一致，行为不变；yaml 显式写入后由 yaml 为准
- [后续变更无意引入硬编码] → spec 场景「新规则参数先入 yaml」作为 review 检查点；docs/runtime-params.md 同步
- [pydantic 校验错误信息定位] → pydantic 自带字段路径错误，满足 fail-fast 场景

## Migration Plan

1. config.py 3 字段 + chains.yaml global 节 3 键
2. pipeline.py / telegram_bot.py 改读配置
3. 测试：GlobalCfg 默认值断言 + 既有测试全量通过
4. 部署后无行为变化（默认一致）；`/status` 正常即验证

## Open Questions

- 无
