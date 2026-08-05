# narrative-block-enrichment Tasks

## 1. 叙事服务升级

- [x] 1.1 `narrative.py`：`NARRATIVE_MAX_LEN` 60→100；`SYSTEM_PROMPT` 重写为 6 维（主题/定位含发行平台/社区热度/风险/开发者发币历史/聪明钱·老鼠仓信号），强制「只能引用给定数值，不得编造数字或链接」
- [x] 1.2 `_infer` user prompt 注入真实数据：launchpad_platform、stat.creator_created_count、stat.top_rat_trader_percentage、stat.top_bundler_trader_percentage、wallet_tags_stat.smart_wallets（缺失维度省略）
- [x] 1.3 新增 `extract_social_links(info) -> list[str]`：短标签映射（X/官网/TG/社区(cto_flag)/DC/YT/IG/TT），每类型取第一个去重，全部超链接，`·` 分隔；X 用户名 `[A-Za-z0-9_]{1,15}` 校验；gmgn/geckoterminal 跳过；非法/缺失省略

## 2. 叙事块渲染

- [x] 2.1 `telegram_notify.py`：`render_narrative_block(info, line)` 输出 `📚 {句}` + `🔗 {' · '.join(链接)}`（无链接时仅 📚 行）；HTML 转义保持
- [x] 2.2 确认 signal（edit_candidate_with_narrative 已传 info）与 query（_enrich_query_narrative 已传 info）两路径自动受益

## 3. 测试

- [x] 3.1 链接提取测试：短标签映射（X/官网/TG/社区(cto_flag)）、`·` 分隔单行、去重、注入字符/超长用户名/tweet URL 路径省略、伪装域名仍为超链接但标签无域名（弹窗兜底）；🔗 行不被二次转义
- [x] 3.2 叙事块渲染测试：📚+🔗 两行、无链接仅 📚、字数 ≤100 截断
- [x] 3.3 叙事块并入 `test_all_cards_html_is_well_formed` 守卫（含超链接）；「句子 N/A 仅 🔗 行」渲染用例
- [x] 3.4 全量 `pytest` 通过

## 4. 部署观察

- [x] 4.1 提交推送 + 部署；观察有社交信息的 token 底部出现 🔗 行、N/A token 行为不变
