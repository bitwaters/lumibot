# telegram-card-redesign Tasks

## 1. 基础设施

- [x] 1.1 在 `telegram_notify.py` 新增 `_esc()` HTML 转义封装（`html.escape(quote=False)`），确认所有外部数据（symbol/name/address/platform/**新闻标题**）只经此入口
- [x] 1.2 `TelegramNotifier.send_text` / `edit_text` 增加 `parse_mode: str | None = "HTML"` 参数；确认 `/chatid` 等裸数据回复显式传 `parse_mode=None`
- [x] 1.3 按钮组重构：`gmgn_keyboard` 扩展为链感知双按钮（GMGN 恒定 + DexScreener 仅 sol/bsc），替换所有调用点
- [x] 1.4 `telegram_bot.py` 全部命令回复（/start /help /positions /stats /rejects /alerts /status /rounds /reset_paper /fallback，共 15 处 `message.answer`）改为 `parse_mode="HTML"`；仅 `/chatid` 保持 `parse_mode=None`
- [x] 1.5 `append_news_line` 对新闻行内容（OpenNews 外部 title）经 `_esc()` 转义后再插入卡片

## 2. 信号推送卡

- [x] 2.1 重写 `render_card`：HTML 富文本；标题 `📡 $SYM · CHAIN`（双源徽标条件出现）；`📍 CA:` + `<code>` 等宽块
- [x] 2.2 指标区：`📊 指标` 分节标题 + 两两一行（值加粗）；市值行恢复触发参照 `→ 触发 $X (+Y%)`（仅信号源）；新增 `1H 成交`（volume_1h）、`平台`、`Top10 持有`
- [x] 2.3 安全行：`🛡 通过` + `买税 X% · 卖税 Y%`（仅 >0）+ 警告 + Rug/Bundler；状态行合并延迟：`✅ 已开仓 $20.00 · ⏱ 延迟 1.8s`
- [x] 2.4 确认 `append_news_line` 在 HTML 下 📰 行为不变（删旧行 + 追加到最后一行文本）；缺指标 `—` 占位保留

## 3. 平仓 / 回本卡

- [x] 3.1 `PaperTradeEvent` 新增 `sell_mode: str = "notional"`；executors.py stage1 事件构造处填充 `order.stage1_sell_mode`
- [x] 3.2 重写 `render_paper_event`：标题含加粗 PnL；`📍 CA:` code 块；`入场市值 → 平仓市值/减仓市值`；`投入` 替换 `名义`；价格回退行改 `入场价/现价/峰值` 标注
- [x] 3.3 回本卡按模式分版：notional → `📌 已回本 · 剩余仓位零成本`；ratio → `📌 剩余仓位成本按减仓价计算`；`回收约 $X · 剩余仓位继续持有`

## 4. 命令卡

- [x] 4.1 `render_positions`：节标题/头行加粗、CA 行改 code 块、`名义` → `投入`、价格回退行加「价」
- [x] 4.2 `render_stats`：`名义` → `投入`、节标题与数值加粗、注脚去 `close_reason=` 术语
- [x] 4.3 `render_rounds`：`均赢` → `均盈`、`均亏 $-X` → `均亏 -$X`、节标题加粗
- [x] 4.4 `render_rejects` / `render_status` / `render_alerts`：节标题/值加粗、CA 行 code
- [x] 4.5 `render_reset_paper` / `render_reset_paper_hint`：`仓位行` → `持仓`、提示卡删除「快照」、数值加粗
- [x] 4.6 `render_help`：`盈利 X% 触发回本减仓`、`减仓 回收本金`、`筛选通过`（替代 过门/门控）、`滑点 买入/卖出`、`剩余仓位峰值回撤`、节标题加粗
- [x] 4.7 全项目 grep 确认 `名义`/`24h量`/`均赢`/`仓位行`/`过门` 等废弃术语不再出现在任何卡片输出
- [x] 4.8 快捷指令菜单：重排 `BOT_COMMANDS_COMMON` / `BOT_COMMANDS_PRIVATE_ONLY` 顺序（positions/stats/alerts/status/rejects/rounds/help/start + reset_paper/chatid），描述统一名词式；`render_help` 命令表同步新顺序；群组排除 reset_paper、保留 chatid

## 5. 测试

- [x] 5.1 重写 `tests/test_telegram_card.py`：新版式断言（标题/CA code/分节/加粗/字段）；含 `PEPE<3` 转义用例；sell_mode 两模式用例；`test_bot_quick_commands` 命令顺序与描述断言更新为新菜单
- [x] 5.2 修订 `test_opennews.py`、`test_telegram_all_chats.py`、`test_pipeline_integration.py`（297-300 行旧卡片断言）等引用旧卡片文本的测试
- [x] 5.3 全量 `pytest` 通过

## 6. 文档

- [ ] 6.1 部署后观察：信号卡首推 → 状态 edit → 新闻 edit 三态正常；群组/私聊均正常
