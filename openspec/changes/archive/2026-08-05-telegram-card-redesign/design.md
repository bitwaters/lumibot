# telegram-card-redesign Design

## Context

现有全部卡片（信号推送、平仓/回本、命令回复）均为 `parse_mode=None` 纯文本：`telegram_notify.py` 的 render_* 返回普通字符串，`telegram_bot.py` 与 `pipeline.py` 直接发送。痛点：无视觉层次、逐行 emoji 噪音、CA 裸文本、信息密度失衡（缺 volume_1h/platform/tax）、单按钮、字段术语误导（`名义` 实为单仓投入金额）。

约束：信号卡有「send → status edit → news edit」的就地编辑生命周期，重渲染必须字节级稳定；全部渲染函数在 `tests/test_telegram_card.py` 被逐字符串断言；`openspec/specs/telegram-cards/spec.md` 定义了版式意图。

## Goals / Non-Goals

**Goals:**
- 统一 HTML 富文本版式语言（加粗值、分节标题、CA code 块、双按钮）
- 信号卡对标行业结构：符号主角标题、`📍 CA:` 等宽块、📊 指标分节、🛡 安全分区、状态行合并延迟
- 字段语义修正（投入/1H 成交/买税卖税/入场价等）与新增字段（1H 成交、平台、税）
- 回本卡按 sell_mode 分版成本表述
- send/edit/news 三路生命周期保持不变，edit 稳定

**Non-Goals:**
- 复制按钮 / 正文内点击复制实体（Bot API 无此实体，见 Decisions）
- 交易按钮（BUY/SELL 等）——本项目是信号 + Paper bot
- 自定义 emoji / 彩色文本（需 premium，且实体列表不支持颜色）
- Rich Messages（Bot API 10.1+，2026-06 发布，客户端兼容风险）
- 修改 pipeline 的推送/开仓/新闻顺序逻辑

## Decisions

1. **HTML parse_mode，不用原生 entities**  
   所有 render_* 继续返回 `str`（HTML 字符串），send/edit/news 三路只增加 `parse_mode="HTML"` 传参，零结构改动。  
   *备选*：原生 MessageEntity 数组——需 render 返回 (text, entities) 并做 UTF-16 offset 计算，edit 流重构面大；收益仅为 date_time 实体（本设计未用）。  
   aiogram 自带 `hbold/hcode/hpre/hblockquote/hlink` 帮手（`aiogram.utils.markdown`），无需自写。

2. **统一转义漏斗 `_esc()`**  
   新增模块级 `_esc()` 封装 `html.escape(..., quote=False)`，所有外部数据（symbol/name/address/platform）必须经它；内部标签/emoji/数字为可信内容。所有 render_* 只通过这一个入口转义外部值，杜绝漏网。

3. **CA 呈现：`📍 CA:` + `<code>` 等宽块；不加复制按钮**  
   调研确认：Bot API（截至 10.2）**没有**正文内可点击复制的实体；唯一一键复制机制是 `CopyTextButton`（内联键盘按钮）。用户决策：不加复制按钮，CA 以等宽 code 块呈现、长按选择复制（业界信号卡标准做法，如 `📍 Mint:` 格式）。此约束写进 spec。

4. **信号卡结构与编辑稳定性**  
   结构固定为：标题行 → `📍 CA:` code 行 → `📊 指标` 分节 → 两两一行指标（值加粗）→ `🛡` 安全行（含买税/卖税/警告/Rug）→ 状态行（状态 + 延迟）→ 📰 新闻行（异步 edit 追加）→ 按钮组。  
   每次 edit 用同一 render_card（同一 cand/paper）重渲染，字节级一致 → 无闪烁；`append_news_line` 的「删除旧 📰 行 + 追加新行」语义保留。  
   *备选*：等宽全对齐指标表（风格 B）——移动端窄屏折行破坏对齐，且不解决层次问题，已否决。

5. **按钮组：GMGN 恒定 + DexScreener 链感知**  
   `[GMGN]` 全链；`[DexScreener]` 仅 sol/bsc（robinhood 无对应页面）。渲染函数输出 `InlineKeyboardMarkup`，send/edit 共用，与现 `gmgn_keyboard` 同构。

6. **`PaperTradeEvent.sell_mode` 字段**  
   仅 stage1 事件需要。executors.py:226 构造处有 `order.stage1_sell_mode`（StrategyOrder 自带，config 默认 `notional`），直接填充；事件为内存态，无 DB 迁移。render 按模式输出：notional → `📌 已回本 · 剩余仓位零成本`；ratio → `📌 剩余仓位成本按减仓价计算`。

7. **字段语义修正落点**  
   `名义` → `投入`（/positions /stats 平仓卡 /help）；`24h量` → `1H 成交`（数据源本就是 volume_1h，旧卡从未展示）；`税 5/5%` → `买税 X% · 卖税 Y%`（仅税 >0 时）；`Top10 22%` → `Top10 持有 22%`；价格回退行加「价」后缀（`入场价/现价/峰值`，$ 符号已暗示市值语境）；`仓位行` → `持仓`；`均赢` → `均盈` 且统一 `-$X` 格式；/help `回本触发` → `盈利 X% 触发回本减仓`、`过门/门控` → `筛选通过`、`滑点 买/卖` → `买入/卖出`、`回本名义` → `回收本金`；/stats 注脚去 `close_reason=` 术语。

8. **parse_mode 传参方式**  
   `TelegramNotifier.send_text/edit_text` 增加 `parse_mode: str | None = "HTML"` 参数；render_* 输出 HTML，业务调用（pipeline/bot）不传即 HTML。/chatid 等裸数据回复显式传 `parse_mode=None`。

## Risks / Trade-offs

- [HTML 转义遗漏导致卡片渲染失败] → 单一 `_esc()` 漏斗 + 测试用例覆盖含 `<`/`&` 的 symbol
- [edit 重渲染与首发不一致（闪烁）] → 同一 render_card 全量重渲，数据不变输出不变；新闻行 replace 语义保留
- [旧测试大量重写] → test_telegram_card.py 按新格式重写断言；test_opennews / test_telegram_all_chats / test_telegram_destinations 检查是否引用旧卡片文本并同步修订
- [sell_mode 缺失默认值] → 字段默认 `"notional"`，与 config 默认一致，旧构造不传时行为正确
- [group 场景按钮/卡片兼容] → HTML 是 Telegram 最老的富文本格式，全客户端支持；无新依赖
- [术语修正遗漏] → 审查报告逐卡核对（17 项清单），spec 中以 MUST 固化

## Migration Plan

1. 实现 `_esc()` + render_* 重构（信号卡 → 平仓/回本卡 → 命令卡），`PaperTradeEvent.sell_mode` 与 executors 填充
2. 更新 `parse_mode` 传参；重写 `tests/test_telegram_card.py`，修订其余受影响测试
3. 全量 `pytest` 通过后部署（`./scripts/deploy_remote.sh`）
4. 观察：信号卡首推/状态 edit/新闻 edit 三态正常；群组与私聊均正常
5. 回滚：卡片为无状态渲染，还原代码即还原旧格式，无数据迁移

## Open Questions

- 无。
