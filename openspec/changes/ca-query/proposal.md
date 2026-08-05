# ca-query

## Why

运营/群组成员经常在聊天里贴合约地址（CA）想快速看 token 信息，当前 bot 只回「未知指令」。主流 meme bot（Skeleton Scan Bot、GMGN 系）都已支持「粘贴 CA 即扫」：自动识别地址、自动判定链、返回信息卡。本项目数据管道（token_info / security / 卡片渲染）已具备，只差消息入口与链判定。

## What Changes

- **消息自动识别 CA**：fallback 处理器在回复「未知指令」前先做 CA 提取——`0x` + 40 hex → EVM 地址；base58 40-44 字符 → Solana 地址；消息内嵌、带前后缀均可识别。一条消息多个 CA 只取第一个。
- **链自动判定**：
  - base58 → `sol`（格式唯一，不探测）
  - `0x` 地址 → 按序探测**已启用链**（`ca_query.probe_order` 配置，默认 bsc → robinhood）：`get_token_info` 404/空数据 → 换下一链；成功即返回。eth/base 等未启用链不探测。
- **查询信息卡**：复用现有卡片语言（`📍 CA:` code 块、📊 指标等宽网格、🛡 安全行、GMGN+DexScreener 链感知按钮），标题用 `🔍 $SYM · CHAIN` 区分查询与信号推送（`📡`）；比信号卡多一行**价格**；无状态行/延迟/新闻行。
- **安全查询只展示不拒答**：`get_token_security` + `evaluate_safety` 照常组装安全行，但 hard_fail 不阻止回复（与信号管道的行为区分）。
- **防滥用**：每 chat 查询节流（`global.ca_query.min_interval_sec`，默认 5s）；`get_token_info` 缓存 300s / security 缓存 3600s 使重复查询免费；GMGN 429/IP 挂起时回复友好错误而非崩溃。
- 回复用 `message.reply`（引用原消息）；授权范围与现有命令一致（私聊 + 授权群组）。

## Capabilities

### New Capabilities

- `ca-query`: CA 提取、链自动判定（格式 + 探针）、查询信息卡渲染、查询节流与降级

### Modified Capabilities

- `telegram-cards`: 新增查询卡版式（🔍 标题、价格行、无状态行），与信号卡共享指标网格/安全行/按钮语言

## Impact

- 代码：`src/lumibot/telegram_notify.py`（新增 `render_query_card`，复用 `_metric_row`/`_safety_line`/`gmgn_keyboard`）；`src/lumibot/telegram_bot.py`（fallback 扩展 + `_extract_ca` + 链探针 + 节流字典）；`src/lumibot/config.py` + `config/chains.yaml`（`global.ca_query`）
- 行为：**非命令文本消息**不再一律回「未知指令」——含 CA 的消息触发查询卡片（授权 chat 内）
- 依赖：无新增；GMGN `/v1/token/info` 与 `/v1/token/security` 既有端点
- 测试：正则提取、链探针（fake client 404→换链）、卡片渲染（含价格行/网格/HTML 合法性并入现有守卫测试）、节流
- 未知项：GMGN 错误链下 `/v1/token/info` 的返回形态（404 异常 vs 空 dict）需实施时 spike 验证
