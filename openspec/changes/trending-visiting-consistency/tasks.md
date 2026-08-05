# trending-visiting-consistency Tasks

## 1. 核心修复

- [x] 1.1 `pipeline.py` `_handle_trending`：`need_visiting_from_info=False` → `True`（trending visiting 门禁统一走 token info）
- [x] 1.2 `filters.py`：`merge_info_fields` force_visiting 注释更新（覆盖语义适用于 signal+trending）；`apply_light_filters` 中 `visiting_min_trending` 注释更新（不再与载荷滞后相关）
- [x] 1.3 `config/chains.yaml`：sol 的 `visiting_min_trending` 注释更新为「同口径额外门槛」

## 2. 测试

- [x] 2.1 `test_visiting.py`：`test_trending_visiting_not_overwritten_by_info` / `test_trending_visiting_not_filled_from_info_when_missing` 改为 force_visiting=True 语义（载荷被覆盖；缺失保持 None）
- [x] 2.2 `test_pipeline_integration.py`：trending visiting 相关断言核对修订（如 trending 门禁改用 info visiting 的用例）
- [x] 2.3 `test_filters.py`：`visiting_min_trending` 用例核对（knob 保留，仅注释变化）
- [x] 2.4 全量 `pytest` 通过

## 3. 部署

- [x] 3.1 提交推送 + `./scripts/deploy_remote.sh`；确认启动无错误

## 4. Spike 与阈值校准

- [ ] 4.1 部署后观察 `/rejects`：visiting 拦截量上升幅度；抽查 token_info visiting 分布（RH/BSC 各 ≥30 个样本）
- [ ] 4.2 按分布重设 RH/BSC `visiting_min`（若分布系统性偏低则调低/禁用）；更新 `docs/runtime-params.md` 相关行
- [ ] 4.3 评估 sol `visiting_min_trending=250` 与 `visiting_min=350` 在新口径下是否收敛，决策并落地
