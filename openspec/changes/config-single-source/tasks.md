# config-single-source Tasks

## 1. 配置迁移

- [x] 1.1 `config.py` GlobalCfg 新增 `manage_interval_sec: float = 5.0` / `dual_source_ttl_sec: float = 30.0` / `alerts_per_chain: int = 5` / `trending_defer_budget: float = 4.0`
- [x] 1.2 `config/chains.yaml` global 节补 3 键（含注释说明归属）
- [x] 1.3 `pipeline.py`：`_loop_manage` 间隔改为 `app_cfg.global_.manage_interval_sec + random.uniform(0, 2)`；`_dual_source_ttl_sec` 从 `app_cfg.global_.dual_source_ttl_sec` 读取（删除硬编码常量）
- [x] 1.4 `telegram_bot.py`：`ALERTS_PER_CHAIN` 改为从 `app_cfg.global_.alerts_per_chain` 读取
- [x] 1.5 `pipeline.py` `_loop_trending`：`available() < 4` 改为 `< app_cfg.global_.trending_defer_budget`

## 2. 测试

- [x] 2.1 配置加载测试：GlobalCfg 3 键默认值断言；yaml 覆盖生效断言
- [x] 2.2 pipeline / telegram_bot 相关测试核对（manage 间隔、dual source ttl、alerts 条数行为不变）
- [x] 2.3 全量 `pytest` 通过

## 3. 文档与校验

- [x] 3.1 `docs/runtime-params.md`：补 3 键说明；「manage 循环间隔硬编码 5s」注记更新为配置化
- [x] 3.2 `openspec validate` 通过；部署后 `/status` 正常验证无行为变化
