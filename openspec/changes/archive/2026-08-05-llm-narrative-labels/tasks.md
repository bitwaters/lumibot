## 1. 配置与数据模型

- [x] 1.1 `src/lumibot/config.py`：新增 `NarrativeCfg`（enabled/base_url/model/timeout_sec/min_symbol_len/symbol_blocklist/cache_ttl_sec），`GlobalCfg` 增加 `narrative: NarrativeCfg | None = None`；`Settings` 增加 `narrative_api_key: str = ""`（env `NARRATIVE_API_KEY`）
- [x] 1.2 `config/chains.yaml`：`global.narrative` 段（enabled: false, base_url: https://api.deepseek.com, model: deepseek-chat, timeout_sec: 10, min_symbol_len: 3, symbol_blocklist: [], cache_ttl_sec: 3600）
- [x] 1.3 `.env.example` 增加 `NARRATIVE_API_KEY=` 占位

## 2. 叙事服务（src/lumibot/narrative.py）

- [x] 2.1 `NarrativeClient`：urllib 实现 OpenAI 兼容 `POST {base_url}/chat/completions`（Bearer 认证、response_format=json_object、temperature=0、max_tokens=128、timeout=timeout_sec）；非 2xx/异常抛出
- [x] 2.2 `NarrativeCache`：dict + TTL，键 `(chain, address)`，只缓存非空结果；`get/set/clear`
- [x] 2.3 `NarrativeService`：`narrative_for(cand, info)` —— 短符号（<min_symbol_len）/黑名单跳过（symbol 统一 lower 比较）→ 缓存 → LLM → JSON 解析 `narrative` 字段 → 截断 30 字 → 空/N/A 返回 None；任何异常返回 None；prompt 输入取 `cand.symbol/name` 与 `(info.get("link") or {}).get("description"/"website")`（link 缺失时 None 安全）
- [x] 2.4 `NarrativeService` 构造时校验：无 api_key 时抛出/标记不可用（由 __main__ 决定不装配）

## 3. 卡片追加与通知

- [x] 3.1 `src/lumibot/telegram_notify.py`：`append_narrative_line(card, line)`（删除旧 📚 行后追加，`_esc` 转义，前缀 📚）
- [x] 3.2 `TelegramNotifier.edit_candidate_with_narrative(cand, paper, *, latency_sec, message_ids, narrative_line)`：`edit_text(append_narrative_line(render_card(...)))`，保留 `gmgn_keyboard` 按钮

## 4. Pipeline 集成

- [x] 4.1 `src/lumibot/pipeline.py`：`ChainPipeline.__init__` 增加可选 `narrative: NarrativeService | None = None` 参数与字段
- [x] 4.2 `_enrich_and_process`：`exec_result.status == "opened"` 且 `sent_message_ids` 非空时，调用 `_spawn_narrative(cand, info, exec_result, message_ids)`（`info` 为 `_fresh_quote` 返回值，避免额外 API 请求）
- [x] 4.3 `_spawn_narrative`：异步任务 → `await service.narrative_for(cand, info)`（超时由 client 内部 `timeout_sec` 控制，不另包 wait_for）→ 有结果才 `edit_candidate_with_narrative`；任务注册进 `self._tasks` 并带清理回调；narrative 为 None 时直接返回
- [x] 4.4 `src/lumibot/__main__.py`：`global.narrative.enabled and settings.narrative_api_key` 时构造 NarrativeService 并传入各 ChainPipeline；enabled 但缺 key 打 warning（不装配）

## 5. 测试

- [x] 5.1 `tests/test_narrative.py`：NarrativeClient mock 正常返回/JSON 解析/超时/异常 → narrative_for 结果与 None 路径
- [x] 5.2 缓存命中不重复调用；N/A 不缓存不展示；短符号/黑名单跳过
- [x] 5.3 `tests/test_telegram_card.py`：`append_narrative_line` 追加/替换/转义/None 原样；`edit_candidate_with_narrative` 保留按钮
- [x] 5.4 `tests/test_pipeline_integration.py`：opened 后触发叙事 edit（FakeNarrative）；非 opened（already_open/blocked）不触发；narrative None 时不 edit
- [x] 5.5 全量 `pytest` 通过

## 6. 文档与部署

- [x] 6.1 `docs/runtime-params.md`：`global.narrative` 键位与 `NARRATIVE_API_KEY` 环境变量说明
- [x] 6.2 本地 `.env` 填写 `NARRATIVE_API_KEY`（用户提供 DeepSeek key），`enabled: true` 后提交推送部署，验证日志与卡片 📚 行
