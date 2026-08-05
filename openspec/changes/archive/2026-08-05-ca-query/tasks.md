# ca-query Tasks

## 1. 配置与识别

- [x] 1.1 `config.py` 新增 `global.ca_query` dataclass（`enabled: bool = True` / `min_interval_sec: float = 5.0` / `probe_order: list[str] = ["bsc", "robinhood"]`）；`config/chains.yaml` 补默认节
- [x] 1.2 `telegram_bot.py` 新增模块级正则常量（EVM `\b0x[0-9a-fA-F]{40}\b`、Solana `\b[1-9A-HJ-NP-Za-km-z]{40,44}\b`）与纯函数 `_extract_ca(text) -> str | None`（取首个匹配）

## 2. 链判定与查询

- [x] 2.1 新增 `_query_token(client, addr, enabled_chains, app_cfg)`：base58 → `["sol"]`；`0x` → 已启用 EVM 链按 `ca_query.probe_order` 顺序探针 `get_token_info`；404 异常/空 dict/无有效字段（symbol/market_cap/price 全空）→ 换链；全 miss 返回未找到
- [x] 2.2 命中后 `merge_info_fields` 组装候选 + `get_token_security` + `evaluate_safety`（fail-open，hard_fail 不拒答；security 失败时安全行标未知）
- [x] 2.3 `render_query_card(cand)`：🔍 标题、`📍 CA:` code、指标网格（💰 价格行 + 💰 市值行 + 开盘/流动性 + 持有人/Top10 + 热度/1H 成交 + 平台）、`_safety_line` 复用、无状态行；按钮复用 `gmgn_keyboard`
- [x] 2.4 fallback 扩展：`_authorized` 后先 `_extract_ca` → 命中则节流检查（每 chat ≥ `min_interval_sec`，超频回「查询太频繁」）→ 查询 → `message.reply`（HTML + 按钮）；GMGN 异常回「暂时不可用，稍后再试」；未命中走原「未知指令」
- [x] 2.5 spike：真实 GMGN 端点验证错误链下 `/v1/token/info` 返回形态（404 vs 200 空体），按实际行为微调命中判定

## 3. 测试

- [x] 3.1 新建 `tests/test_ca_query.py`；`_extract_ca` 单测：EVM/内嵌文本/多 CA 取首/Solana base58/无 CA
- [x] 3.2 探针单测（fake client）：sol 直接命中；bsc 命中不探 rh；bsc 404 → rh 命中；全 miss 未找到
- [x] 3.3 `render_query_card` 测试：标题/价格行/网格/安全行/无状态行；缺指标 `—`；hard_fail 仍出卡
- [x] 3.4 节流测试：超频提示；GMGN 异常降级提示
- [x] 3.5 查询卡并入 `test_all_cards_html_is_well_formed` 守卫
- [x] 3.6 全量 `pytest` 通过

## 4. 部署观察

- [x] 4.1 查询卡 LLM 叙事：`build_dispatcher` 接收 `narrative`；`_handle_ca_message` 回复前 `narrative_for` + `append_narrative_line`（fail-open）；`__main__` 传入 narrative_service
- [x] 4.1 查询卡 LLM 叙事（异步 edit + 数据行）
- [x] 4.2 数据修复：市值 = price×supply 计算；volume 从 price 对象提取（flatten 提升）；叙事块 60 字 + 数据行（24h 涨跌/买卖笔数）
- [x] 4.3 部署后私聊/群组各发带 CA 消息验证：sol base58、bsc 0x、robinhood 0x 各一条（含 📚 叙事行）；`/status` 观察配额占用无异常
