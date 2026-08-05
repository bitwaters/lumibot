# ca-query Design

## Context

bot 当前对一切非命令文本回复「未知指令」（`telegram_bot.py` fallback）。数据管道已齐备：`GmgnClient.get_token_info`（缓存 300s）/`get_token_security`（缓存 3600s）、`merge_info_fields`（filters.py）、`evaluate_safety`（safety.py）、卡片渲染语言（`_metric_row`/`_safety_line`/`gmgn_keyboard`）。

约束：GMGN 全局限流 ~1 req/s，信号推送是主任务，查询不得挤占；`_request` 对 HTTP ≥400 抛 RuntimeError；robinhood 与 bsc 同为 `0x` EVM 地址，格式无法区分，必须探测。

## Goals / Non-Goals

**Goals:**
- 消息内嵌 CA 自动识别（EVM + Solana），链自动判定，零用户输入
- 查询卡复用信号卡版式语言，多一行价格，🔍 标识身份
- 安全查询只展示不拒答；失败降级友好
- 每 chat 节流 + 缓存复用，保护信号管道配额
- 全部逻辑收在 telegram_bot fallback + telegram_notify 新 render，不触碰 pipeline/executors

**Non-Goals:**
- 交易/买入入口（查询只读）
- eth/base 等未启用链探测
- 24h 涨跌/5m-24h 多维度量能（本期只加价格）
- 下钻按钮（Top Holders/Whales 等 Skeleton 式深查）
- 消息内多个 CA 全部应答

## Decisions

1. **识别正则**
   - EVM: `\b0x[0-9a-fA-F]{40}\b`
   - Solana: `\b[1-9A-HJ-NP-Za-km-z]{40,44}\b`
   - 取首个匹配；正则放 `telegram_bot.py` 模块级常量，纯函数 `_extract_ca(text) -> str | None` 便于单测。
   - *备选*：43-44 严格长度可减误报，但 40-44 覆盖全 Solana 生态；`1-9` 开头与全角边界约束已足够。

2. **链判定 = 格式映射 + 有序探针**（spike 验证 2026-08-05）  
   - base58 → `["sol"]`，零探测。  
   - `0x` → `enabled_chains(app_cfg)`（config.py 现成 helper）中 EVM 格式链，按 `global.ca_query.probe_order` 顺序（默认 `["bsc", "robinhood"]`）。  
   - **spike 结论：GMGN 对错误链返回 200 + 空壳 dict（`symbol=''`、`address=''`、price 全 0），不是 404 异常**。命中判定 = 返回 `address` 匹配请求地址且 `symbol` 非空（或 mc 非空）；空壳/空 dict → 换链。404 异常兜底保留（`if "404" in str(exc): continue`），其余异常（429/IP 挂起）立即上抛 → 处理器降级回复。
   - 命中后补 `get_token_security`（fail-open）。全 miss → 「未找到合约（支持 sol/bsc/robinhood）」。

3. **卡片组装复用现有路径**
   - 候选构造 `TokenCandidate(chain, address, source=Source.TRENDING)`（source 仅作必填字段，查询卡渲染不读）；`merge_info_fields(cand, info, force_visiting=True)` 填充；`evaluate_safety(chain_cfg.safety_profile, normalize_security(sec), chain_cfg.safety)` 得安全行。
   - `render_query_card(cand)`: 标题 `🔍 {hbold('$'+sym)} · {chain_tag}`；`📍 CA:` code；`📊 指标` 网格 = 价格行（💰 价格，独占）+ 市值行（💰 市值，独占，无触发参照）+ 开盘/流动性 + 持有人/Top10 + 热度/1H 成交 + 聪明钱/KOL（`wallet_tags_stat.smart_wallets/renowned_wallets`，spike 验证两链返回）+ 平台；`_safety_line` 原样复用；无状态行。
   - **LLM 叙事（📚）**：查询回复前 `await narrative.narrative_for(cand, info)`（复用 NarrativeService，走其缓存与 eligibility），命中则 `append_narrative_line` 追加 `📚` 行作为末行；失败/不可用 fail-open 不影响回复。查询是交互式单次回复（用户已在等待），不做信号卡的异步 edit 流程。
   - 查询硬失败（hard_fail）不拒答——与信号管道 `_reject` 路径分叉，仅渲染警告。

4. **节流与降级**
   - `global.ca_query.min_interval_sec`（config.py 新增 dataclass 字段，yaml 默认 5）。
   - dispatcher 内 `dict[chat_id, ts]` 节流表（与既有命令一致的内存态即可）；超频 → 「查询太频繁，请稍后再试」。
   - GMGN 异常（429/IP 挂起 RuntimeError）→ 「GMGN 暂时不可用，请稍后再试」；不重试（避免放大限流）。
   - 缓存命中查询零 API 成本（决策 2 走 `use_cache=True` 默认路径）。

5. **回复方式与作用域**
   - `message.reply(text, parse_mode="HTML", reply_markup=gmgn_keyboard(...))`；授权逻辑沿用 `_authorized`。

## Risks / Trade-offs

- [Solana 正则误报（40-44 位 base58 长词）] → 节流限频 + 查询只读无副作用；概率低可接受
- [探针消耗配额（0x 地址 miss 一次 = 1 请求）] → 仅已启用链（≤2）、缓存复用、节流；bsc 优先命中率高
- [错误链返回形态未知] → 命中判定兼容 404 与空体两种；实现时 spike 确认
- [群组刷屏触发查询] → 每 chat 节流默认 5s；config 可调
- [查询与信号管道并发抢配额] → 共享同一限流桶（client._request 内部），天然排队；查询失败友好降级不影响信号

## Migration Plan

1. 实现 `_extract_ca` + 探针 + `render_query_card` + 节流 + config
2. 单测（正则/探针 fake client/卡片/节流/HTML 合法性并入现有守卫）
3. spike 验证 GMGN 错误链返回形态后按真实行为微调命中判定
4. 部署后：私聊/群组各发一条带 CA 消息验证；`/status` 观察配额占用

## Open Questions

- 是否需要显式 `/ca <addr>` 命令作为补充入口？（本期不含，纯自动识别）
