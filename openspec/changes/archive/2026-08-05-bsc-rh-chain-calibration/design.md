## Context

现状：`AppConfig.strategy` 全局一份，所有 `PaperExecutor` 共用；`/stats` 聚合全库 `paper_positions`，`/status` 只取「第一条 enabled 链」的 mode。BSC/RH 仍为 draft。用户约束：**三链策略只写在 `config/chains.yaml` 且彼此独立；TG 汇总卡必须分链显示，禁止混总。**

校准流程：`docs/calibration.md`。数值真源：仅 yaml（见 `docs/runtime-params.md`）。

## Goals / Non-Goals

**Goals:**

- yaml：`chains.<name>.strategy` 为该链唯一策略定义；删除（或忽略）顶层全局 `strategy` 运行路径
- 执行 / `/help` / 校验只读链级 strategy；其它文件不维护策略数字副本
- `/stats`、`/status`（及同类总览）按 `sol` / `bsc` / `robinhood`（已启用者）分段
- BSC → RH 分阶段校准启用；限流紧张时只动新链 interval
- 门禁：`enabled ⇒ calibrated`；profile：`sol↔sol_v1`、`bsc|rh↔evm_v1` 加载失败

**Non-Goals:**

- Live swap / quote 白名单强制
- 在 OpenSpec / README / TG 文案里另写一套「现行 -30%」类数字作为真源（只允许举例并指向 yaml）
- 一次 deploy 同时首开 BSC+RH（除非限流已书面评估）

## Decisions

1. **策略配置形状**  
   ```yaml
   chains:
     sol:
       strategy:
         notional_usd: 20
         hard_stop_pct: -0.30
         # ...
       filters: ...
     bsc:
       strategy: { ... }  # 独立，可与 sol 不同
   ```  
   迁移：把现行顶层 `strategy` **原样写入** `chains.sol.strategy`；BSC/RH 初值可复制同一份，之后只改本链。加载后若仍存在顶层 `strategy`：迁移期可警告并忽略，或校验失败——选定 **忽略并 log warning**，避免旧文件直接炸；新提交的仓库 yaml 删除顶层块。  
   _备选：保留全局作 default、链上 override → 拒用（用户要求唯一真源在三链块，不要两处写策略）。_

2. **「不要在其他地方写策略」**  
   - 代码默认值仅作 pydantic 结构默认（反序列化缺省），**不以**其冒充现行运营参数  
   - `/help` 对每个 enabled 链渲染该链 `strategy` + 滑点  
   - `docs/runtime-params.md` 只列键名与「真源=yaml 分链 strategy」，不抄数字  
   - 单测断言读 fixture yaml，不写死与生产 yaml 绑定的魔法百分比（除非测公式）

3. **校准状态机（闭合鸡生蛋）**  
   门禁要求 enable 前必须 `calibrated`。可执行顺序：  
   1) 连通性（仍 disabled）  
   2) `calibrated` + `enabled`（进入 Paper 试跑；此时策略/门禁已按该链 yaml）  
   3) 只调该链 `filters|safety|sources|execution|strategy`  
   4) 收敛后保持 `calibrated`；更新 calibration 表  
   「Paper 完成才允许写 calibrated」不可行，本设计明确废弃该顺序。更新 `docs/calibration.md` 与此对齐。

4. **TG 分链汇总**  
   - `/stats`：对每个 enabled 链（或三链凡有数据者）输出一块：`[SOL]` / `[BSC]` / `[RH]`，含持仓、名义、已平、本轮开仓、跳过、硬止损占比、最近平仓（该链）  
   - `/status`：每链一行或一块：enabled、mode、open、active cooldowns  
   - `/positions`：多链有仓时按链分组标题  
   - `/alerts`：按链分组；**每链各自取最近 N 条**（默认 N=5）再拼接，禁止「全局 LIMIT 10 再分组」（会饿死低频链）  
   - `/rejects`：已按 chain 行展示；可按链分组增强（可选）  
   - DB：`paper_stats_summary(chain=…)`、`count_active_cooldowns(chain=…)`、`list_recent_alerts(chain=…, limit=…)`；TG 路径不传混总主摘要  

5. **按链 `/reset_paper`（必做，BREAKING）**  
   - `/reset_paper sol confirm` | `bsc` | `robinhood`：只清该链；`/reset_paper all confirm`：全清  
   - 裸 `/reset_paper`、旧式 `/reset_paper confirm`（无 scope）：提示用法，**不得**删除  
   - **无 `chain` 列的表**（`paper_fills` / `snapshots`）MUST 经 position 子查询删除，同一 `BEGIN IMMEDIATE` 事务内顺序固定：  
     1) `DELETE FROM paper_fills WHERE position_id IN (SELECT id FROM paper_positions WHERE chain=?)`  
     2) `DELETE FROM snapshots WHERE position_id IN (SELECT id FROM paper_positions WHERE chain=?)`  
     3) `DELETE FROM paper_positions WHERE chain=?`  
     4) `DELETE FROM paper_skip_opens WHERE chain=?`  
     5) `DELETE FROM cooldowns WHERE chain=?`  
     6) `DELETE FROM alerts WHERE chain=?`  
     7) `DELETE FROM reject_counts WHERE chain=?`  
   - `all`：保持现有整表 DELETE（或对三链循环上述步骤）  
   - 远程脚本可选 `CHAIN=`；默认全清并在注释标明

6. **BSC 先于 RH；改动隔离**  
   首开 BSC 的 deploy 中 RH 保持 `enabled: false`。PR 可改任意链自己的块；禁止用「为了 BSC」去改 SOL 策略——SOL 策略只在调 SOL 时改。

7. **Profile 绑定（必做）**  
   加载期校验链名与 `safety_profile`；错配 `ValidationError`。

8. **限流**  
   共享 `global.rate_limit`；压力下先改新链 `sources.*.interval_sec` 或关其 trending。

9. **测试**  
   - 加载：三链各自 strategy 不同 → executor 用对值  
   - `paper_stats_summary("sol")` 不含 bsc 行；`reset_paper_experiment("bsc")` 不动 sol  
   - `render_stats` / `render_status` / `render_alerts` 分链且数字/条目不混加  
   - `evm_v1` missing 字段；TG BSC/RH 链接  

## Risks / Trade-offs

- [yaml 迁移漏写某链 strategy] → 加载校验每个 chain 必须有 strategy 块  
- [顶层 strategy 残留被误读] → 忽略 + warning；CI/审观看 diff  
- [误用 all 清三链] → 提示文案强调 `sol|bsc|robinhood`；试跑文档写优先 `/reset_paper bsc confirm`  
- [EVM 字段缺失全灭] → 连通性 go/no-go  
- [帮助/alerts 卡片变长] → 只渲染 enabled 链；alerts 固定每链 N 条  

## Migration Plan

1. 代码支持 `chains.*.strategy` + 分链 stats/TG/alerts + 按链 reset；兼容读入时忽略顶层 `strategy`  
2. 改 yaml：SOL/BSC/RH 写入独立 strategy；删顶层  
3. 部署 SOL-only 验证（行为与现网一致；`/reset_paper sol confirm` 冒烟）  
4. 连通性 → BSC calibrated+enabled → Paper 调 **bsc 块** → 稳定  
5. RH 同理  
6. 回滚某链：`enabled: false`；策略回滚只还原该链 yaml 块  

## Open Questions

- BSC/RH strategy 初值完全复制 SOL，还是 Paper 前就先改（默认：复制 SOL 现网 `strategy` 值；`execution.slippage` 已分链保持 8%）  
