const state = {
  data: null,
  chart: "equity",
  table: "trades",
};

const actionLabel = {
  LONG_SIGNAL: "多头确认",
  HOLD_LONG: "持有",
  REDUCE: "减仓",
  SHORT_CLEAR: "空头清仓",
  ANCHOR_BREAK_CLEAR: "跌破锚点",
  WAIT: "等待",
};

const tradeActionLabels = {
  "买入": "买入",
  "减仓": "减仓",
  "清仓": "清仓",
  "持有": "持有",
  "等待": "等待",
};

const regimeLabel = {
  LONG: "多头",
  SHORT: "空头",
  NEUTRAL: "中性",
};

const fmtPercent = new Intl.NumberFormat("zh-CN", {
  style: "percent",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const fmtMoney = new Intl.NumberFormat("zh-CN", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

const fmtNumber = new Intl.NumberFormat("zh-CN", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
});

/* ── 数据加载 ── */
async function loadData() {
  showSkeletons();
  const response = await fetch(`./data/dashboard.json?ts=${Date.now()}`);
  if (!response.ok) {
    throw new Error(`数据加载失败：HTTP ${response.status}`);
  }
  state.data = await response.json();
  showMessage("", "hidden");
  hideSkeletons();
  render();
}

function showSkeletons() {
  const ms = document.getElementById("metricsSkeleton");
  if (ms) ms.classList.remove("hidden");
  const mc = document.getElementById("metricsContent");
  if (mc) mc.classList.add("hidden");
  const cs = document.getElementById("chartSkeleton");
  if (cs) cs.classList.remove("hidden");
  const chart = document.getElementById("mainChart");
  if (chart) chart.classList.add("hidden");
  const ts = document.getElementById("tableSkeleton");
  if (ts) ts.classList.remove("hidden");
  const tc = document.getElementById("tableContent");
  if (tc) tc.classList.add("hidden");
}

function hideSkeletons() {
  const ms = document.getElementById("metricsSkeleton");
  if (ms) ms.classList.add("hidden");
  const mc = document.getElementById("metricsContent");
  if (mc) mc.classList.remove("hidden");
  const cs = document.getElementById("chartSkeleton");
  if (cs) cs.classList.add("hidden");
  const chart = document.getElementById("mainChart");
  if (chart) chart.classList.remove("hidden");
  const ts = document.getElementById("tableSkeleton");
  if (ts) ts.classList.add("hidden");
  const tc = document.getElementById("tableContent");
  if (tc) tc.classList.remove("hidden");
}

function render() {
  renderHeader();
  renderMetrics();
  renderStateList();
  renderChart();
  renderTable();
}

function renderHeader() {
  const generated = state.data?.generated_at || "--";
  document.getElementById("generatedAt").textContent = `数据更新时间 ${generated}`;
}

function renderMetrics() {
  const summary = state.data.summary || {};
  setMetric("totalReturn", fmtPercentValue(summary.total_return), summary.total_return);
  setMetric("maxDrawdown", fmtPercentValue(summary.max_drawdown), summary.max_drawdown);
  setMetric("endingValue", summary.ending_value ? fmtMoney.format(summary.ending_value) : "--");
  setMetric("tradeCount", String(summary.trades ?? "--"));
  setMetric("latestRegime", regimeLabel[summary.latest_regime] || summary.latest_regime || "--");
}

function setMetric(id, text, signedValue = null) {
  const el = document.getElementById(id);
  el.textContent = text;
  el.classList.remove("positive", "negative");
  if (signedValue === null || signedValue === undefined) return;
  if (Number(signedValue) > 0) el.classList.add("positive");
  if (Number(signedValue) < 0) el.classList.add("negative");
}

function renderStateList() {
  const summary = state.data.summary || {};
  const latestSignal = last(state.data.signals) || {};
  const rows = [
    ["区间", `${summary.start_date || "--"} 至 ${summary.end_date || "--"}`],
    ["策略信号", summary.latest_signal_label || "--"],
    ["交易动作", tradeActionLabels[summary.latest_trade_action] || summary.latest_trade_action || "--"],
    ["仓位状态", summary.latest_position_status || "--"],
    ["当前持仓", summary.latest_etf || "--"],
    ["触发原因", summary.latest_reason_label || latestSignal.reason_label || latestSignal.reason || "--"],
  ];

  document.getElementById("stateList").innerHTML = rows
    .map(
      ([label, value]) => `
        <div class="state-item">
          <div class="state-label">${escapeHtml(label)}</div>
          <div class="state-value">${escapeHtml(value)}</div>
        </div>
      `,
    )
    .join("");
}


/* ── ECharts 图表 ── */
let chartInstance = null;

function initChart() {
  const dom = document.getElementById("mainChart");
  if (!dom) return null;
  if (chartInstance) {
    chartInstance.dispose();
    chartInstance = null;
  }
  if (dom.offsetWidth === 0 || dom.offsetHeight === 0) return null;
  chartInstance = echarts.init(dom, null, { renderer: "canvas" });
  return chartInstance;
}

function renderChart() {
  document.querySelectorAll("[data-chart]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.chart === state.chart);
    btn.setAttribute("aria-selected", String(btn.dataset.chart === state.chart));
  });
  const activeChartTab = document.querySelector(`[data-chart="${state.chart}"]`);
  document.getElementById("chartPanel").setAttribute("aria-labelledby", activeChartTab?.id || "chartTabEquity");

  const title = document.getElementById("chartTitle");
  const meta = document.getElementById("chartMeta");
  const empty = document.getElementById("emptyChart");

  const chart = initChart();
  if (!chart) {
    empty.classList.remove("hidden");
    return;
  }

  let ok = false;
  if (state.chart === "equity") {
    title.textContent = "净值曲线";
    meta.textContent = "组合单位净值与交易信号";
    ok = drawEquityChart(chart);
  } else if (state.chart === "amv") {
    title.textContent = "0AMV 波段";
    meta.textContent = "+4%、-1.5%、-2.3% 阈值状态";
    ok = drawAmvChart(chart);
  } else {
    title.textContent = "回撤曲线";
    meta.textContent = "基于单位净值计算";
    ok = drawDrawdownChart(chart);
  }

  empty.classList.toggle("hidden", ok);
  if (ok) {
    chart.resize();
    // 窗口 resize 监听
    if (!chart._resizeHandler) {
      chart._resizeHandler = () => chart.resize();
      window.addEventListener("resize", chart._resizeHandler);
    }
  }
}

/* ── ECharts 主题色 ── */
const ecTheme = {
  gridColor: "#edf0f4",
  axisColor: "#4a5568",
  axisLineColor: "#d8dee7",
  equityLine: "#2563eb",
  amvLine: "#334155",
  upColor: "#cc2b1d",
  downColor: "#0b6848",
  amberColor: "#7a4f00",
  tooltipBg: "#fff",
  tooltipBorder: "#d8dee7",
};

/* ── 通用 ECharts 配置 ── */
function ecBaseOption() {
  return {
    color: ["#2563eb", "#334155"],
    grid: { left: 60, right: 20, top: 20, bottom: 14 },
    xAxis: {
      type: "category",
      axisLine: { lineStyle: { color: ecTheme.axisLineColor } },
      axisTick: { alignWithLabel: true },
      axisLabel: { color: ecTheme.axisColor, fontSize: 11 },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value",
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: ecTheme.axisColor, fontSize: 11 },
      splitLine: { lineStyle: { color: ecTheme.gridColor } },
    },
    dataZoom: [
      {
        type: "inside",
        start: 0,
        end: 100,
        minValueSpan: 10,
      },
      {
        type: "slider",
        start: 0,
        end: 100,
        height: 20,
        bottom: 0,
        borderColor: ecTheme.axisLineColor,
        backgroundColor: "rgba(0,0,0,0.02)",
        fillerColor: "rgba(37,99,235,0.15)",
        handleStyle: { borderColor: ecTheme.axisLineColor, color: "#fff" },
        textStyle: { color: ecTheme.axisColor, fontSize: 10 },
      },
    ],
    tooltip: {
      trigger: "axis",
      backgroundColor: ecTheme.tooltipBg,
      borderColor: ecTheme.tooltipBorder,
      borderWidth: 1,
      textStyle: { color: "#17202a", fontSize: 12 },
      confine: true,
    },
  };
}

/* ── 构建信号标注数据 ── */
function buildSignalScatter(dates, values) {
  const signalMap = new Map((state.data.signals || []).map((s) => [s.date, s]));
  const result = [];
  dates.forEach((date, i) => {
    const signal = signalMap.get(date);
    if (signal && signal.action !== "WAIT" && signal.action !== "HOLD_LONG") {
      result.push({
        value: [i, values[i]],
        itemStyle: { color: actionColor(signal.action) },
        signalName: actionLabel[signal.action] || signal.action,
      });
    }
  });
  return result;
}

/* ── 净值曲线 ── */
function drawEquityChart(chart) {
  const data = state.data.portfolio || [];
  if (!data.length) return false;

  const dates = data.map((d) => d.date);
  const values = data.map((d) => Number(d.unit_net_value));
  const signals = buildSignalScatter(dates, values);

  const base = ecBaseOption();
  base.xAxis.data = dates;
  base.tooltip = {
    ...base.tooltip,
    formatter: function (params) {
      if (!params || !params.length) return "";
      const p = params[0];
      const idx = p.dataIndex;
      const date = dates[idx];
      const val = idx != null && idx < values.length ? values[idx] : null;
      let html = `<strong>${date}</strong><br/>净值 ${val != null ? val.toFixed(3) : "--"}`;
      const sp = params.find((pp) => pp.seriesName === "信号");
      if (sp) {
        const sig = (state.data.signals || []).find((s) => s.date === date);
        if (sig) {
          html += `<br/>信号 ${actionLabel[sig.action] || sig.action}`;
          if (sig.reason) html += `<br/>原因 ${escapeHtml(sig.reason)}`;
        }
      }
      return html;
    },
  };
  base.series = [
    {
      name: "净值",
      type: "line",
      data: values,
      smooth: true,
      lineStyle: { color: ecTheme.equityLine, width: 2 },
      areaStyle: { color: "rgba(37,99,235,0.06)" },
      symbol: "none",
      connectNulls: true,
      animationDuration: 800,
    },
    signals.length
      ? {
          name: "信号",
          type: "scatter",
          data: signals,
          symbol: "circle",
          symbolSize: 8,
          itemStyle: { borderColor: "#fff", borderWidth: 2 },
          z: 10,
          animationDuration: 600,
        }
      : null,
  ].filter(Boolean);
  chart.setOption(base, true);
  return true;
}

/* ── 0AMV 波段 ── */
function drawAmvChart(chart) {
  const data = state.data.signals || [];
  if (!data.length) return false;

  const dates = data.map((d) => d.date);
  const values = data.map((d) => Number(d.close));
  const signals = buildSignalScatter(dates, values);

  const base = ecBaseOption();
  base.xAxis.data = dates;
  base.tooltip = {
    ...base.tooltip,
    formatter: function (params) {
      if (!params || !params.length) return "";
      const p = params[0];
      const idx = p.dataIndex;
      const row = idx != null && idx < data.length ? data[idx] : null;
      if (!row) return `<strong>${dates[idx]}</strong>`;
      let html = `<strong>${row.date}</strong><br/>`;
      html += `收盘 ${Number(row.close).toFixed(2)}<br/>`;
      html += `涨跌幅 ${fmtPercentValue(row.pct_change)}<br/>`;
      html += `状态 ${regimeLabel[row.regime] || row.regime}`;
      if (row.action !== "WAIT" && row.action !== "HOLD_LONG") {
        html += `<br/>信号 ${actionLabel[row.action] || row.action}`;
      }
      if (row.selected_etf) html += `<br/>ETF ${escapeHtml(row.selected_etf)}`;
      if (row.reason) html += `<br/>原因 ${escapeHtml(row.reason)}`;
      return html;
    },
  };
  base.series = [
    {
      name: "0AMV",
      type: "line",
      data: values,
      smooth: true,
      lineStyle: { color: ecTheme.amvLine, width: 2 },
      areaStyle: { color: "rgba(51,65,85,0.06)" },
      symbol: "none",
      connectNulls: true,
      animationDuration: 800,
    },
    signals.length
      ? {
          name: "信号",
          type: "scatter",
          data: signals,
          symbol: "circle",
          symbolSize: 8,
          itemStyle: { borderColor: "#fff", borderWidth: 2 },
          z: 10,
          animationDuration: 600,
        }
      : null,
  ].filter(Boolean);
  chart.setOption(base, true);
  return true;
}

/* ── 回撤曲线 ── */
function drawDrawdownChart(chart) {
  const data = state.data.portfolio || [];
  if (!data.length) return false;

  const dates = data.map((d) => d.date);
  let peak = -Infinity;
  const values = data.map((d) => {
    const v = Number(d.unit_net_value);
    peak = Math.max(peak, v);
    return v / peak - 1;
  });

  const base = ecBaseOption();
  base.xAxis.data = dates;
  base.tooltip = {
    ...base.tooltip,
    formatter: function (params) {
      if (!params || !params.length) return "";
      const p = params[0];
      const idx = p.dataIndex;
      const date = dates[idx];
      const val = idx != null && idx < values.length ? values[idx] : null;
      return `<strong>${date}</strong><br/>回撤 ${val != null ? fmtPercent.format(val) : "--"}`;
    },
    valueFormatter: (v) => fmtPercent.format(v),
  };
  base.yAxis = {
    ...base.yAxis,
    max: 0,
    axisLabel: {
      color: ecTheme.axisColor,
      fontSize: 11,
      formatter: (v) => fmtPercent.format(v),
    },
  };
  base.series = [
    {
      name: "回撤",
      type: "line",
      data: values,
      smooth: true,
      lineStyle: { color: ecTheme.upColor, width: 2 },
      areaStyle: { color: "rgba(204,43,29,0.12)" },
      symbol: "none",
      connectNulls: true,
      animationDuration: 800,
    },
  ];
  chart.setOption(base, true);
  return true;
}

/* ── 表格筛选 ── */
const filterState = {
  trades: { dateStart: "", dateEnd: "", type: "", search: "" },
  signals: { dateStart: "", dateEnd: "", type: "", search: "" },
};

/* ── 完整交易分组逻辑 ── */
function computeTransactions() {
  const trades = state.data.trades || [];
  const txns = [];
  let cur = null;
  let pos = 0;

  for (const t of trades) {
    if (cur === null) {
      cur = { oid: t.order_book_id, symbol: t.symbol, start_date: t.datetime, trades: [], total_buy_val: 0, total_sell_val: 0, total_fees: 0 };
      pos = 0;
    }
    cur.trades.push(t);
    cur.total_fees += t.cost || 0;
    if (t.side === 'BUY') {
      pos += t.quantity;
      cur.total_buy_val += t.quantity * t.price;
    } else {
      pos -= t.quantity;
      cur.total_sell_val += t.quantity * t.price;
    }
    if (pos === 0) {
      cur.end_date = t.datetime;
      cur.gross_pnl = cur.total_sell_val - cur.total_buy_val;
      cur.net_pnl = cur.gross_pnl - cur.total_fees;
      cur.return_pct = cur.total_buy_val > 0 ? cur.net_pnl / cur.total_buy_val : 0;
      const start = new Date(cur.start_date.slice(0, 10));
      const end = new Date(cur.end_date.slice(0, 10));
      cur.hold_days = Math.round((end - start) / 86400000);
      cur.buys = cur.trades.filter(t => t.side === 'BUY').length;
      cur.sells = cur.trades.filter(t => t.side === 'SELL').length;
      txns.push(cur);
      cur = null; pos = 0;
    }
  }
  if (cur !== null) {
    cur.end_date = null;
    cur.gross_pnl = 0;
    cur.net_pnl = 0;
    cur.return_pct = 0;
    const start = new Date(cur.start_date.slice(0, 10));
    cur.hold_days = Math.round((Date.now() - start) / 86400000);
    cur.buys = cur.trades.filter(t => t.side === 'BUY').length;
    cur.sells = cur.trades.filter(t => t.side === 'SELL').length;
    txns.push(cur);
  }
  return txns.reverse();
}

let txnExpandState = {};

function renderTransactionsTable() {
  const txns = computeTransactions();
  document.getElementById("tableTitle").textContent = "完整交易";
  document.getElementById("tableMeta").textContent = `${txns.filter(t => t.end_date).length} 笔已完成`;

  setTable(
    null,
    txns.length,
    ["", "标的", "建仓日", "清仓日", "持有时长", "交易次数", "建仓金额", "平仓金额", "毛利", "净利", "收益率"],
    txns.map((txn, i) => {
      const isOpen = !txn.end_date;
      const id = `txn-${i}`;
      const expanded = txnExpandState[i] || false;
      const toggleIcon = expanded ? '▼' : '▶';

      const netPnlColor = txn.net_pnl >= 0 ? 'class="positive"' : 'class="negative"';
      const grossPnlColor = txn.gross_pnl >= 0 ? 'class="positive"' : 'class="negative"';
      const retColor = txn.return_pct >= 0 ? 'class="positive"' : 'class="negative"';

      const label = isOpen ? '进行中' : txn.end_date.slice(0, 10);
      const holdLabel = isOpen ? `${txn.hold_days}天(进行中)` : `${txn.hold_days}天`;
      const actionCount = `${txn.buys}买${txn.sells}卖`;

      const detailRows = expanded ? txn.trades.map(t => {
        const d = t.datetime.slice(0, 10);
        const sideTag = t.side === 'BUY'
          ? tag('买入', 'tag-buy')
          : tag('卖出', 'tag-sell');
        return `<tr class="txn-detail"><td></td><td colspan="2">${d}</td><td>${sideTag.html}</td><td class="numeric">${fmtMoney.format(t.quantity)}</td><td class="numeric">${fmtNumber.format(t.price)}</td><td class="numeric">${fmtNumber.format(t.cost)}</td><td colspan="4"></td></tr>`;
      }).join('') : '';

      const arrowBtn = `<span class="txn-toggle" data-txn="${i}" style="cursor:pointer;user-select:none;font-size:12px">${toggleIcon}</span>`;

      return [
        { html: arrowBtn },
        txn.symbol || txn.oid,
        txn.start_date.slice(0, 10),
        label,
        holdLabel,
        actionCount,
        { html: `<span class="numeric">${fmtMoney.format(txn.total_buy_val)}</span>` },
        { html: `<span class="numeric">${fmtMoney.format(txn.total_sell_val)}</span>` },
        { html: `<span ${grossPnlColor} class="numeric">${fmtMoney.format(txn.gross_pnl)}</span>` },
        { html: `<span ${netPnlColor} class="numeric">${fmtMoney.format(txn.net_pnl)}</span>` },
        { html: `<span ${retColor} class="numeric">${fmtPercent.format(txn.return_pct)}</span>` },
        { html: detailRows ? `<table class="txn-inner"><tbody>${detailRows}</tbody></table>` : '' },
      ];
    }),
  );

  document.querySelectorAll('.txn-toggle').forEach(el => {
    el.addEventListener('click', (e) => {
      const idx = parseInt(e.target.dataset.txn);
      txnExpandState[idx] = !txnExpandState[idx];
      renderTransactionsTable();
    });
  });
}

function renderTable() {
  document.querySelectorAll("[data-table]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.table === state.table);
    btn.setAttribute("aria-selected", String(btn.dataset.table === state.table));
  });
  const activeTableTab = document.querySelector(`[data-table="${state.table}"]`);
  document.getElementById("tablePanel").setAttribute("aria-labelledby", activeTableTab?.id || "tableTabTrades");
  if (state.table === "trades") renderTradesTable();
  else if (state.table === "txns") renderTransactionsTable();
  else renderSignalsTable();
}

function renderTradesTable() {
  const allRows = state.data.trades || [];
  document.getElementById("tableTitle").textContent = "交易明细";
  document.getElementById("tableMeta").textContent = `${allRows.length} 笔成交`;

  const fs = filterState.trades;
  const filtered = allRows.filter((row) => {
    if (fs.dateStart && row.datetime < fs.dateStart) return false;
    if (fs.dateEnd && row.datetime > fs.dateEnd) return false;
    if (fs.type && row.side !== fs.type) return false;
    if (fs.search) {
      const q = fs.search.toLowerCase();
      if (
        !row.order_book_id?.toLowerCase().includes(q) &&
        !row.symbol?.toLowerCase().includes(q)
      )
        return false;
    }
    return true;
  });

  filtered.sort((a, b) => (b.datetime || "").localeCompare(a.datetime || ""));

  const filterEl = buildFilterBar("trades", [
    { id: "trades-dateStart", label: "起始", type: "date", key: "dateStart" },
    { id: "trades-dateEnd", label: "截止", type: "date", key: "dateEnd" },
    {
      id: "trades-type",
      label: "方向",
      type: "select",
      key: "type",
      options: [
        { value: "", label: "全部" },
        { value: "BUY", label: "买入" },
        { value: "SELL", label: "卖出" },
      ],
    },
    {
      id: "trades-search",
      label: "搜索",
      type: "search",
      key: "search",
      placeholder: "代码/名称",
    },
  ]);

  setTable(
    filterEl,
    filtered.length,
    ["时间", "标的", "名称", "方向", "数量", "价格", "成本"],
    filtered.map((row) => [
      row.datetime,
      row.order_book_id,
      row.symbol,
      tag(row.side, row.side === "BUY" ? "tag-buy" : "tag-sell"),
      numeric(fmtMoney.format(row.quantity)),
      numeric(fmtNumber.format(row.price)),
      numeric(fmtNumber.format(row.cost)),
    ]),
  );
}

function renderSignalsTable() {
  const allRows = state.data.signals || [];
  document.getElementById("tableTitle").textContent = "信号与交易";
  document.getElementById("tableMeta").textContent = `${allRows.length} 个交易日`;

  const fs = filterState.signals;
  const filtered = allRows.filter((row) => {
    if (fs.dateStart && row.date < fs.dateStart) return false;
    if (fs.dateEnd && row.date > fs.dateEnd) return false;
    if (fs.type && row.trade_action !== fs.type) return false;
    if (fs.search) {
      const q = fs.search.toLowerCase();
      if (
        !row.holding_etf?.toLowerCase().includes(q) &&
        !row.selected_etf?.toLowerCase().includes(q) &&
        !row.selected_concept?.toLowerCase().includes(q)
      )
        return false;
    }
    return true;
  });

  filtered.sort((a, b) => (b.date || "").localeCompare(a.date || ""));

  const filterEl = buildFilterBar("signals", [
    { id: "signals-dateStart", label: "起始", type: "date", key: "dateStart" },
    { id: "signals-dateEnd", label: "截止", type: "date", key: "dateEnd" },
    {
      id: "signals-type",
      label: "交易动作",
      type: "select",
      key: "type",
      options: [
        { value: "", label: "全部" },
        { value: "买入", label: "买入" },
        { value: "减仓", label: "减仓" },
        { value: "清仓", label: "清仓" },
        { value: "持有", label: "持有" },
        { value: "等待", label: "等待" },
      ],
    },
    {
      id: "signals-search",
      label: "搜索",
      type: "search",
      key: "search",
      placeholder: "标的/概念",
    },
  ]);

  setTable(
    filterEl,
    filtered.length,
    ["日期", "涨跌幅", "策略信号", "交易动作", "仓位状态", "持仓标的", "选中标的", "触发原因"],
    filtered.map((row) => [
      row.date,
      numeric(fmtPercentValue(row.pct_change)),
      tag(row.signal_label || actionLabel[row.action] || row.action, signalClass(row.signal_label || row.action)),
      tag(tradeActionLabels[row.trade_action] || row.trade_action, tradeActionClass(row.trade_action)),
      row.position_status || (row.target_weight >= 0.99 ? "满仓" : row.target_weight > 0 ? "半仓" : "空仓"),
      row.holding_etf || "",
      row.selected_etf || "",
      row.reason_label || row.reason || "",
    ]),
  );
}


function buildFilterBar(tableName, fields) {
  const existing = document.getElementById(`filterBar-${tableName}`);
  if (existing) return existing;
  const bar = document.createElement("div");
  bar.id = `filterBar-${tableName}`;
  bar.className = "filter-bar";
  bar.innerHTML =
    fields
      .map((f) => {
        if (f.type === "select") {
          return `<label>${escapeHtml(f.label)}
          <select id="${f.id}" data-table="${tableName}" data-key="${f.key}">
            ${f.options
              .map((o) => `<option value="${escapeHtml(o.value)}">${escapeHtml(o.label)}</option>`)
              .join("")}
          </select>
        </label>`;
        }
        return `<label>${escapeHtml(f.label)}
        <input type="${f.type}" id="${f.id}" data-table="${tableName}" data-key="${f.key}"
          ${f.placeholder ? `placeholder="${escapeHtml(f.placeholder)}"` : ""} />
      </label>`;
      })
      .join("") +
    `<span class="filter-count" id="filterCount-${tableName}"></span>`;
  bar.addEventListener("change", onFilterChange);
  bar.addEventListener("input", onFilterChange);
  return bar;
}

function onFilterChange(e) {
  const target = e.target;
  const tableName = target.dataset.table;
  const key = target.dataset.key;
  if (!tableName || !key) return;
  filterState[tableName][key] = target.value;
  if (state.table === tableName) renderTable();
}

function setTable(filterEl, count, headers, rows) {
  const tablePanel = document.getElementById("tablePanel");
  const existing = document.getElementById(`filterBar-${state.table}`);
  if (filterEl) {
    if (existing && existing !== filterEl) {
      existing.replaceWith(filterEl);
    } else if (!existing) {
      tablePanel.parentNode.insertBefore(filterEl, tablePanel);
    }
    const countEl = document.getElementById(`filterCount-${state.table}`);
    if (countEl) countEl.textContent = `${count} 条`;
  } else {
    // Remove filter bar if it exists
    if (existing) existing.remove();
  }
  document.getElementById("tableHead").innerHTML = `<tr>${headers.map((h) => `<th>${escapeHtml(h)}</th>`).join("")}</tr>`;
  document.getElementById("tableBody").innerHTML = rows
    .map(
      (row) => {
        const cells = row.map((cell) => `<td${cell?.numeric ? ' class="numeric"' : ""}>${cell?.html ?? escapeHtml(String(cell ?? ""))}</td>`).join("");
        // If last cell has nested table (detail), separate it
        const lastCell = row[row.length - 1];
        if (lastCell && lastCell.html && lastCell.html.includes('txn-inner')) {
          const mainCells = row.slice(0, -1).map((cell) => `<td${cell?.numeric ? ' class="numeric"' : ""}>${cell?.html ?? escapeHtml(String(cell ?? ""))}</td>`).join("");
          return `<tr>${mainCells}</tr><tr class="txn-detail-row"><td colspan="${headers.length}">${lastCell.html}</td></tr>`;
        }
        return `<tr>${cells}</tr>`;
      },
    )
    .join("");
}

function tag(text, className) {
  return { html: `<span class="tag ${className}">${escapeHtml(text)}</span>` };
}

function numeric(text) {
  return { html: escapeHtml(text), numeric: true };
}

function signalClass(signalLabel) {
  if (signalLabel && signalLabel.includes("多头确认")) return "tag-long";
  if (signalLabel && signalLabel.includes("空头清仓")) return "tag-short";
  if (signalLabel && signalLabel.includes("跌破锚点")) return "tag-short";
  if (signalLabel && signalLabel.includes("减仓")) return "tag-reduce";
  return "tag-neutral";
}

function actionClass(action) {
  if (action === "LONG_SIGNAL") return "tag-long";
  if (action === "SHORT_CLEAR" || action === "ANCHOR_BREAK_CLEAR") return "tag-short";
  if (action === "REDUCE") return "tag-reduce";
  return "tag-neutral";
}

function tradeActionClass(tradeAction) {
  if (tradeAction === "买入") return "tag-long";
  if (tradeAction === "清仓") return "tag-short";
  if (tradeAction === "减仓") return "tag-reduce";
  return "tag-neutral";
}

/* A股配色：红涨绿跌 */
function actionColor(action) {
  if (action === "LONG_SIGNAL") return ecTheme.upColor;
  if (action === "REDUCE") return ecTheme.amberColor;
  if (action === "SHORT_CLEAR" || action === "ANCHOR_BREAK_CLEAR") return ecTheme.downColor;
  return "#64748b";
}

function fmtPercentValue(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return fmtPercent.format(Number(value));
}

function showMessage(message, tone = "info") {
  const el = document.getElementById("appMessage");
  el.textContent = message;
  el.className = `notice ${tone}`;
  el.classList.toggle("hidden", !message);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function last(items) {
  return items && items.length ? items[items.length - 1] : null;
}

/* ── 事件绑定 ── */
document.querySelectorAll("[data-chart]").forEach((btn) => {
  btn.addEventListener("click", () => {
    state.chart = btn.dataset.chart;
    renderChart();
  });
});

document.querySelectorAll("[data-table]").forEach((btn) => {
  btn.addEventListener("click", () => {
    state.table = btn.dataset.table;
    renderTable();
  });
});

document.querySelectorAll("[role='tablist']").forEach((tablist) => {
  tablist.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    const tabs = [...tablist.querySelectorAll("[role='tab']")];
    const currentIndex = tabs.indexOf(document.activeElement);
    if (currentIndex < 0) return;

    event.preventDefault();
    let nextIndex = currentIndex;
    if (event.key === "ArrowLeft") nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
    if (event.key === "ArrowRight") nextIndex = (currentIndex + 1) % tabs.length;
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = tabs.length - 1;

    tabs[nextIndex].focus();
    tabs[nextIndex].click();
  });
});

document.getElementById("refreshBtn").addEventListener("click", () => {
  loadData().catch((error) => {
    showMessage(`${error.message}。请先运行 .\\scripts\\run_backtest.ps1 生成 dashboard.json。`, "error");
  });
});

/* ── 数据更新 / 回测按钮 ── */
const fullUpdateBtn = document.getElementById("fullUpdateBtn");
const updateBtn = document.getElementById("updateDataBtn");
const backtestBtn = document.getElementById("runBacktestBtn");
const overlay = document.getElementById("progressOverlay");
const progressBody = document.getElementById("progressBody");
const progressTitle = document.getElementById("progressTitle");
const progressStatus = document.getElementById("progressStatus");
const closeBtn = document.getElementById("progressCloseBtn");

let currentTaskId = null;
let pollTimer = null;

function startTask(endpoint, title, disableBtn) {
  if (currentTaskId) return;
  disableBtn.disabled = true;
  fullUpdateBtn.disabled = true;
  updateBtn.disabled = true;
  backtestBtn.disabled = true;
  progressBody.textContent = "启动中...";
  progressTitle.textContent = title;
  progressStatus.innerHTML = '<span class="progress-spinner"></span>运行中';
  overlay.classList.remove("hidden");

  fetch(endpoint, { method: "POST" })
    .then((r) => r.json())
    .then((data) => {
      currentTaskId = data.task_id;
      pollProgress();
    })
    .catch((err) => {
      progressBody.textContent += "\n--- 错误: " + err.message + " ---";
      finishTask();
    });
}

function pollProgress() {
  if (!currentTaskId) return;
  fetch(`/api/progress-json/${currentTaskId}`)
    .then((r) => r.json())
    .then((data) => {
      if (data.output && data.output.length) {
        progressBody.textContent = data.output.join("\n");
        progressBody.scrollTop = progressBody.scrollHeight;
      }
      if (data.done) {
        finishTask();
        // auto-refresh dashboard after backtest or full update
        if (backtestBtn.disabled || fullUpdateBtn.disabled) {
          setTimeout(() => loadData().catch(() => {}), 500);
        }
      } else {
        pollTimer = setTimeout(pollProgress, 500);
      }
    })
    .catch(() => {
      pollTimer = setTimeout(pollProgress, 1000);
    });
}

function finishTask() {
  currentTaskId = null;
  if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
  progressStatus.innerHTML = "✓ 完成";
  closeBtn.disabled = false;
  fullUpdateBtn.disabled = false;
  updateBtn.disabled = false;
  backtestBtn.disabled = false;
}

fullUpdateBtn.addEventListener("click", () => {
  startTask("/api/run-full-update", "全量更新中...", fullUpdateBtn);
});

updateBtn.addEventListener("click", () => {
  startTask("/api/run-update-data", "更新数据中...", updateBtn);
});

backtestBtn.addEventListener("click", () => {
  startTask("/api/run-backtest", "回测执行中...", backtestBtn);
});

closeBtn.addEventListener("click", () => {
  overlay.classList.add("hidden");
});

loadData().catch((error) => {
  document.getElementById("generatedAt").textContent = "数据未加载";
  showMessage(`${error.message}。请先运行 .\\scripts\\run_backtest.ps1 生成 dashboard.json。`, "error");
});
