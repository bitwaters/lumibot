## Context

信号卡片目前只有链上指标（市值/流动性/热度），缺少代币叙事上下文。第三方新闻源（6551 OpenNews）已移除（服务不可用、无公开注册渠道）。开仓卡片推送链路为：`gate → 推送（首发卡）→ 开仓 → edit 状态行`（见 telegram-card-layout / telegram-cards spec）。本设计在该链路末端追加一个**可选的异步叙事行**，不阻塞推送、不参与门禁。

## Goals / Non-Goals

**Goals:**
- 用 DeepSeek 为实际开仓的代币推断一句话叙事（≤30 汉字），异步追加 📚 行到卡片
- 每币最多 1 次 LLM 调用（TTL 缓存 1h），成本 <¥0.1/天
- 失败/超时/信息不足：卡片保持原样，零副作用
- 所有行为可配置（`global.narrative`），默认关闭

**Non-Goals:**
- 叙事不参与任何筛选/风控/排序（纯展示）
- 不做多轮对话、不做新闻/推文聚合、不做板块图谱
- 不引入额外依赖（用 stdlib urllib，与 GmgnClient 一致，规避 Cloudflare TLS 指纹问题）
- 不做 LLM 输出的事后校验（长度截断即可）

## Decisions

1. **单文件 `src/lumibot/narrative.py`**，含 `NarrativeClient` / `NarrativeCache` / `NarrativeService` 三组件：
   - `NarrativeClient`：`POST {base_url}/chat/completions`，`Authorization: Bearer {api_key}`，`response_format={"type":"json_object"}`，`temperature=0`（求稳定），`max_tokens=128`（30 汉字 + JSON 包装约 80-100 token，64 会截断）；用 `urllib`（不引 httpx），请求超时即 `timeout_sec`（urllib `timeout=` 参数，全链路一次生效）
   - `NarrativeCache`：dict + 过期时间，键 `(chain, address)`；只缓存非空结果
   - `NarrativeService.narrative_for(cand)`：黑名单/短符号 → 缓存 → LLM → JSON 解析 → 截断 30 字；异常一律返回 `None`
2. **Prompt**（`system` + 单条 `user`，中文）：
   ```
   system: 你是加密 meme 币分析助手。根据代币名称、简介和官网域名，用不超过
           30 个汉字的一句话描述它的叙事/主题（如"特朗普概念官方迷因币"、
           "AI Agent 概念"）。信息不足时输出 "N/A"。只输出 JSON: {"narrative": "..."}
   user: symbol={symbol} name={name} desc={description} website={website}
   ```
   - `description`/`website` 来自 token_info 的 `link.description` / `link.website`（`merge_info_fields` 已把 info 并入 cand，但 link 未展平——在 `_spawn_narrative` 调用处传 `cand.raw` 之外的 info 需要额外获取？→ 见 Decision 4）
3. **卡片追加**：`TelegramNotifier` 新增 `edit_candidate_with_narrative(cand, paper, message_ids, narrative_line)`；`append_narrative_line(card, line)` 复用「删旧 📚 行 + 追加」语义（与已移除的 append_news_line 同构，前缀改为 📚）；渲染时先 `render_card(...)` 再追加，保留状态行与 GMGN 按钮
4. **输入数据获取**：叙事输入需要 token_info 的 name/link 字段。开仓路径已有 `_fresh_quote` 返回的 `info`（post-gate 快照，含 name/link），在 pipeline 触发 `_spawn_narrative(cand, info, message_ids)` 时直接传入——不额外发 API 请求
5. **触发时机**：`_enrich_and_process` 中 `exec_result.status == "opened"` 且 `sent_message_ids` 非空 → `asyncio.create_task` 启动叙事任务（任务注册进 `self._tasks` 以便 shutdown 清理）；`news` 编辑链已删除，此为新挂接点
6. **配置**：`global.narrative`（`NarrativeCfg`：enabled/base_url/model/timeout_sec/min_symbol_len/symbol_blocklist/cache_ttl_sec）；`Settings.narrative_api_key`（env `NARRATIVE_API_KEY`）；`__main__.py` 在 `enabled and api_key` 时构造 `NarrativeService` 传入 pipeline，否则 pipeline 内为 None → 快速跳过
7. **超时模型（单层）**：LLM 请求超时由 `NarrativeClient` 内部 urllib `timeout=timeout_sec`（默认 10s）一次控制，`narrative_for` 为纯 `await`，**不再外层包 `wait_for`**（避免 3s 外层把 10s 内部超时截断成半途取消）；edit 环节（`edit_text` 内部 aiogram 调用）有自身超时语义，失败走既有 `edit_text` 的 catch 分支静默保留上一版卡片
8. **无 NARRATIVE_API_KEY 时**：`global.narrative.enabled=true` 但缺 key → 启动日志 warning，服务不装配（与已删除 news 的双重条件一致）

## Risks / Trade-offs

- [LLM 幻觉/错配叙事] → prompt 限定输入来源 + `N/A` 兜底 + 纯展示；错配不造成资金损失，运营肉眼可辨
- [延迟] → 全异步，推送与开仓路径零等待；LLM 超时 10s 后静默放弃
- [成本] → 每币 1 次 + TTL 缓存 + 仅 opened 触发；预留 `max_per_day` 不做（当前量级 <0.1 元/天，超出再补）
- [DeepSeek 不可用] → 静默失败，功能降级为无叙事行；不重试避免雪崩
- [卡片编辑失败] → 保留上一版卡片（edit_text 语义），不重试
- [与并行改动冲突] → 本地存在 `config-single-source` 并行改动（管理间隔等参数 yaml 化），本变更不触碰 `manage_interval_sec`/`dual_source_ttl_sec` 等键，只新增 `global.narrative`
