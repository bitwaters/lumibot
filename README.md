# lumibot

GMGN meme 信号 Telegram bot（Paper 模拟优先）。只在 **IPv4** 网络出站可用时才能调用 GMGN。

## 快速开始

1. 复制环境变量：`cp .env.example .env`，填入 `GMGN_API_KEY`、`TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_IDS`
   - 私聊控制台：`TELEGRAM_CHAT_IDS`（收推送 + 可发命令）
   - 群组推送（可选）：把 bot 拉进群后发 `/chatid`，把返回的负数 id 写入 `TELEGRAM_GROUP_CHAT_IDS`（只推送，不能 `/reset_paper`）
2. 安装：`pip install -e ".[dev]"`
3. 确认本机有 IPv4 出站（双栈/仅 IPv6 会启动失败）
4. 运行：`lumibot` 或 `python -m lumibot`

配置见 `config/chains.yaml`。默认仅启用已校准的 `sol`；`bsc` / `robinhood` 为 `draft` 且禁用。

## IPv4 VPS（推荐）

生产/调试部署在固定公网 IPv4 的 VPS 上。本仓库默认 SSH 主机别名：`lumi-server`（`~/.ssh/config`）。

**数据与代码落在 `/www/lumibot`（大盘）**，SQLite 挂载为 `/www/lumibot/data:/data`，不要写到系统盘 Docker named volume。

### 一次性初始化

```bash
# 1) 推送代码到 GitHub main 后
./scripts/setup_server.sh   # 生成 deploy key → 你贴到 GitHub → clone + scp .env

# 2) 停掉本机同 token 的 bot，再构建启动
./scripts/deploy_remote.sh
```

### 日常调试闭环

```bash
# 本地改完 → commit → push main
git push origin main

# 服务器拉取并重建
./scripts/deploy_remote.sh

# 抓日志
./scripts/logs_remote.sh
# 或：ssh lumi-server 'cd /www/lumibot && docker compose logs --tail=500'
```

### Compose 要点

- 工作目录：`/www/lumibot`
- 数据库：`/www/lumibot/data/lumibot.db` → 容器 `/data/lumibot.db`
- 密钥：`/www/lumibot/.env`（不进 Git）
- 同一 `TELEGRAM_BOT_TOKEN` **不能**本机与服务器同时 long-poll

本地调试若需跳过 IPv4 探测（不推荐）：`LUMIBOT_SKIP_IPV4_CHECK=true`。

## 校准新链

见 [docs/calibration.md](docs/calibration.md)：`draft` → `calibrated` → `enabled`。

## 测试

```bash
pytest
```
