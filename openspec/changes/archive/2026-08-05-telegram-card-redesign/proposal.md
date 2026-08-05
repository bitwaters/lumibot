# telegram-card-redesign

## Why

当前所有回复卡片是纯文本 + 逐行 emoji 排版：无视觉层次（同一字重、数值不突出）、emoji 噪音（每行一个图标 + 「·」串联）、信息密度失衡（CA 裸文本不可选、缺成交量/平台/税字段）、按钮只有 GMGN 一个。对照主流 meme bot（GMGN/Trojan/信号类 bot）的卡片惯例，需要统一重构版式与字段语义。

## What Changes

- **格式化升级**：全部卡片从 `parse_mode=None` 切换为 `parse_mode="HTML"`；数值/标题加粗，外部数据（symbol/name/CA）统一 HTML 转义。
- **信号卡重构**（对标行业结构）：
  - 标题改为符号主角：`📡 $PEPE · SOL · 双源`（📡 为全卡唯一门面 emoji；双源徽标仅存在时出现）
  - CA 独占一行，`📍 CA:` 标签 + `<code>` 等宽块（长按选择复制；**不**加复制按钮）
  - 指标区加「📊 指标」分节标题，指标两两一行、值加粗
  - 新增展示：`1H 成交`（volume_1h）、`平台`（platform）、买卖税（仅 >0 时）
  - 市值行恢复触发参照：`市值 $125K → 触发 $100K (+25%)`
  - 安全/状态分区：`🛡` 行收纳税与警告；状态行 `✅ 已开仓 $20.00 · ⏱ 延迟 1.8s`（edit 目标行）
  - 按钮组：GMGN + DexScreener（链感知，robinhood 无 DexScreener 链接）
- **平仓/回本卡**：同一版式语言（标题含加粗 PnL、CA code 块、双按钮）；`PaperTradeEvent` 新增 `sell_mode` 字段，回本卡按模式分版显示成本表述（notional →「已回本 · 剩余仓位零成本」；ratio →「剩余仓位成本按减仓价计算」）。
- **命令卡统一语言**：节标题/数值加粗，CA 行 code 块；/positions、/stats、/alerts、/rounds、/rejects、/status、/help、/reset_paper 全部纳入。
- **字段语义修正**（见 design.md 术语表）：
  - `名义` → `投入`（notional 实为单仓投入金额）
  - `24h量` → `1H 成交`；`Top10 22%` → `Top10 持有 22%`
  - `税 5/5%` → `买税 5% · 卖税 5%`
  - `仓位行` → `持仓`（去 DB 术语）；`均赢` → `均盈`；`均亏 $-2.30` → `均亏 -$2.30`
  - /help：`回本触发 25%` → `盈利 25% 触发回本减仓`；`过门/门控` → `筛选通过`；`滑点 买/卖` → `买入/卖出`；`减仓 回本名义` → `减仓 回收本金`
  - 价格回退行标注「价」：`入场价 1 → 现价 1.2`
- **快捷指令菜单优化**：私聊/群组菜单按使用频率重排（监控命令 `/positions /stats /alerts /status /rejects /rounds` 置前，配置类 `/chatid` 与 `/start` 殿后）；描述统一「名词式」词法；`/help` 内命令表顺序同步；群组仍排除 `/reset_paper`，保留 `/chatid`（配群必需）。
- **新闻行位置**：保持在卡片最后一行文本（状态行之后、按钮之前），`📰` 前缀与 replace 语义不变。

## Capabilities

### New Capabilities

- `telegram-card-layout`: 新版卡片版式语言（HTML 格式化、分节、CA code 块、双按钮、字段术语）与全部渲染函数的统一实现

### Modified Capabilities

- `telegram-cards`: 信号推送卡从纯文本升级为 HTML 富文本版式；新增展示字段（1H 成交/平台/税）；CA 以 code 块呈现；按钮组扩展；命令/出场卡共享新版式语言
- `telegram-alerts`: exec_status 文本与告警卡渲染随新版式更新（若存在差异）

## Impact

- 代码：`src/lumibot/telegram_notify.py`（全部 render_* 重构 + HTML 转义封装 + 按钮组 + 新闻行转义）；`src/lumibot/telegram_bot.py`（15 处命令回复 `parse_mode` 翻转为 HTML，仅 `/chatid` 保留 None）；`src/lumibot/exec_types.py`（PaperTradeEvent 新增 sell_mode）；`src/lumibot/executors.py`（stage1 事件填充 sell_mode）；`pipeline.py` 经 notifier 默认 parse_mode 零改动
- 依赖：`/rounds` 命令与 `render_rounds` 来自工作区未提交的 `bsc-rh-chain-calibration` 变更；本变更含其卡片改造，需协调两个变更的合并顺序（建议 bsc-rh 先行落地）
- 行为：**BREAKING**——所有卡片文本格式变化；测试断言全部重写
- 测试：`tests/test_telegram_card.py` 重写；`test_opennews.py`、`test_telegram_all_chats.py` 等引用卡片文本的测试修订
- 依赖：无新增（aiogram 3.30 HTML parse_mode 原生支持）
- 文档：`openspec/specs/telegram-cards/spec.md` 更新
