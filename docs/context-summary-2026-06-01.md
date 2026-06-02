# 对话上下文总结 — 2026-06-01

## 项目概况

- **项目**: `amv-rqalpha-backtest` (D:\workSpace\amv-rqalpha-backtest)
- **策略**: 0AMV 多空波段 ETF 择时 + 概念行业轮动选标
- **框架**: RQAlpha，日线频率，`current_bar` 撮合
- **数据源**: TDX .day 文件提取的 AMV 代理序列 + 概念日收益率 CSV

## 当前回测结果

| 指标 | 值 |
|------|------|
| 回测区间 | 2005-01-04 ~ 2026-05-15 |
| 累计收益 | +74.84% |
| 最大回撤 | -51.90% |
| 期末资产 | 1,748,364.67 |
| 交易次数 | 450 |
| 信号行数 | 8,122 |
| 净值天数 | 5,186 |
| 最新状态 | 持有 / 半仓 / 159995.XSHE（半导体芯片ETF） |

## 后端架构

```
scripts/
  export_amv_from_tdx.py   从通达信 .day 提取 AMV 代理序列
  run_backtest.ps1          运行 RQAlpha 回测并导出 dashboard.json
  frontend_agent.ps1        前端自动化审查脚本（新创建）
strategy/
  amv_band_strategy.py      主策略（init / handle_bar）
  amv_rules.py              信号判定逻辑（BandParams / decide_action）
  momentum_selectors.py     概念动量选标
data/
  amv_daily.csv             0AMV 日线
  concept_daily_returns.csv 概念日收益率
  concept_etf_map.csv       概念→ETF 映射
  etf_flow.csv              ETF 候选池
```

## 关键参数

```
BandParams(
    long_threshold=0.04,       # +4% 开多
    reduce_threshold=-0.015,   # -1.5% 减半仓
    short_threshold=-0.023,    # -2.3% 空头清仓
    long_weight=1.0,           # 满仓
    reduce_weight=0.5,         # 减仓系数（当前仓位 × 0.5）
)
MOMENTUM_WINDOW = 5           # 概念动量窗口（5日）
matching_type = current_bar    # 当日 bar 成交
```

## 前端架构

```
web/
  index.html      主页面（骨架屏、指标卡、图表、表格）
  styles.css      CSS 变量体系 + 响应式断点
  app.js          业务逻辑（数据加载、ECharts、筛选、标签切换）
  app.js          Node.js 静态文件服务器（端口 8081）
  data/dashboard.json  回测数据
```

- 纯静态 SPA，使用 ECharts 5.5.0（CDN加载）
- 三个图表 Tab：净值曲线 / 0AMV 波段 / 回撤曲线
- 两个表格 Tab：交易明细 / 信号日志（带日期/方向/搜索筛选）
- 骨架屏 → 内容加载状态切换
- 响应式断点：1020px / 720px
- 服务器: `node web/app.js` (localhost:8081)

## 本回合工作

### 1. 回测数据日期对齐修复
- **问题**: `export_amv_from_tdx.py` 输出 `amv_daily.csv` 包含 2026-05-15 之后的数据
- **方案**: 在 `export_amv_from_tdx.py` 中写入数据前截断到 `last_valid_trade_date`，该日期从通达信 .day 文件末条获取
- **效果**: 信号停在 2026-05-15（周五），交易停在 2026-05-14（最后减仓日），净值停在 2026-05-15，完全对齐

### 2. 减仓/清仓逻辑澄清
- **问题**: 2025-09-03 卖出 402,000 股（减仓），2025-09-04 卖出 402,200 股（也是减仓？），数量一样
- **分析**: 
  - 09-03: AMV 跌 -1.5%，触发 REDUCE → 满仓减半 → 卖 402k
  - 09-04: AMV 跌超 -2.3%，触发 SHORT_CLEAR（优先级高于 REDUCE）→ 剩余半仓全清 → 卖 402k
- **结论**: 行为正确，10-04 是清仓非减半。`amv_rules.py` 中 `SHORT_CLEAR` 分支优先级高于 `REDUCE`

### 3. 前端专家 Agent 创建
- 创建了 `scripts/frontend_agent.ps1` — 可运行的审查/优化/截图脚本
  - `--review` 仅审查
  - `--improve` 审查+改进
  - `--screenshot` 截图
  - `--all` 全部（默认）
- 创建了 `C:\Users\wFei\.codex\skills\frontend-expert\SKILL.md` — Codex 前端技能
- 创建了 `web/_reviews/` 目录存放审查报告和截图

## 技术债务 / 待办

- [ ] 数据跨度问题：`dashboard.json` 的 `signals` 从 1993 年起（远早于回测起始 2005），因为 `decide_action` 对全量 AMV 数据运行，仅 `handle_bar` 按回测区间过滤了交易
- [ ] 最大回撤 -51.9% 偏高，策略在 2015 和 2018 年可能有较大回撤
- [ ] 前端缺少深色模式支持
- [ ] 前端表格缺少 CSV 导出功能
- [ ] Playwright 截图依赖安装状态
