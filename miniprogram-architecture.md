# 微信小程序架构设计方案

> 项目：热带度假 A 股波段监控系统 → 微信小程序
> 目标：快速上线 + 微信生态获客
> 基于现有 Web 版 `monitor20/sites/17-tropical/` 功能迁移

---

## 一、架构总览

### 三层架构

```
┌─────────────────────────────────────────────┐
│  小程序前端（主包 < 2MB + 2 个分包）          │
│  WXML/WXSS/WXS · 3 Tab 页 + 4 分包页         │
│  wx.setStorageSync 存用户偏好                  │
├─────────────────────────────────────────────┤
│  云开发后端                                    │
│  云函数（fetch / query / subscribe / snapshot）│
│  云数据库（实时缓存 + 历史快照）                │
│  云存储（静态资源）                             │
├─────────────────────────────────────────────┤
│  外部数据源（仅云函数可访问，小程序端不可直连）  │
│  新浪 hq · AKShare · Tushare · 乐咕            │
└─────────────────────────────────────────────┘
```

### 核心设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 后端方案 | 微信云开发 | 零运维、免域名备案、天然 HTTPS、定时触发器支持 |
| 数据获取 | 云函数代理 + 云 DB 缓存 | 小程序域名白名单限制，无法直连新浪/AKShare |
| 缓存策略 | 60s TTL + cron 预热 | 交易时间内用户始终秒开，无需等待外部 API |
| 分包策略 | 主包 3 页 + 分包 A(复盘) + 分包 B(社交) | 主包控制在 1.4MB 内，复盘/社交按需加载 |
| 主题方案 | WXSS class 切换（day/night） | 小程序不支持 CSS 变量，用 class 预定义色值 |
| 图表方案 | Canvas 2D API | 小程序不支持 SVG，走势图用 Canvas 重绘 |
| 状态管理 | globalData + 页面 setData | 轻量级，不引入 Mobx 等额外依赖 |

---

## 二、项目目录结构

```
tropical-monitor/
├── app.js                    # App 生命周期 + globalData
├── app.json                  # 全局配置（页面路由、tabBar、分包）
├── app.wxss                  # 全局样式（热带/深海主题色系）
├── project.config.json       # IDE 配置
├── sitemap.json              # 搜索索引配置
│
├── pages/                    # ===== 主包页面 =====
│   ├── index/                # Tab 1: 首页（温度仪表 + 信号 + 指数）
│   │   ├── index.js
│   │   ├── index.json
│   │   ├── index.wxml
│   │   └── index.wxss
│   ├── watchlist/            # Tab 2: 自选股管理
│   │   ├── watchlist.js
│   │   ├── watchlist.json
│   │   ├── watchlist.wxml
│   │   └── watchlist.wxss
│   └── settings/             # Tab 3: 设置（主题 + 关于 + 分享）
│       ├── settings.js
│       ├── settings.json
│       ├── settings.wxml
│       └── settings.wxss
│
├── components/               # ===== 自定义组件 =====
│   ├── temp-gauge/           # 温度仪表盘（进度条 + 判定文字）
│   ├── signal-panel/         # 8 维信号面板（可点击切换）
│   ├── index-list/           # 多市场指数列表（A股/港股/美股）
│   ├── strategy-card/        # 战法匹配 + 风控确认卡片
│   ├── search-bar/           # 股票搜索栏（5534 只全 A 模糊匹配）
│   ├── watchlist-table/      # 自选股表格（含价格/涨跌幅/删除）
│   ├── price-cell/           # 价格单元格（涨红跌绿）
│   ├── theme-toggle/         # 主题切换按钮（白天/夜间）
│   └── about-card/           # 关于卡片（版本 + 数据源说明）
│
├── subpackages/              # ===== 分包 =====
│   ├── review/               # 分包 A: 板块复盘（~400KB）
│   │   ├── pages/
│   │   │   ├── sector/       # 4 榜单 + 走势图
│   │   │   └── history/      # 历史快照时间线
│   │   └── components/
│   │       ├── sector-card/  # 单个榜单卡片
│   │       └── trend-chart/  # Canvas 2D 走势图
│   └── social/               # 分包 B: 社交分享（~200KB, Phase 2）
│       └── pages/
│           ├── invite/       # 邀请卡片生成
│           └── poster/       # 温度海报生成
│
├── utils/                    # ===== 工具函数 =====
│   ├── request.js            # 云函数调用封装（统一错误处理）
│   ├── signals.js            # 8 维信号自动判断逻辑
│   ├── format.js             # 价格/涨跌幅格式化
│   └── store.js              # 全局状态管理（globalData 封装）
│
├── cloudfunctions/           # ===== 云函数 =====
│   ├── fetch/                # 定时数据抓取（cron 60s）
│   │   ├── index.js          # 新浪 hq + AKShare → 云 DB
│   │   ├── package.json      # 依赖：axios, akshare-proxy
│   │   └── config.json       # 定时触发器配置
│   ├── query/                # 按需查询（股票搜索 + 实时行情）
│   │   ├── index.js          # 查缓存 → 未命中回源
│   │   └── package.json
│   ├── subscribe/            # 订阅消息推送调度
│   │   └── index.js
│   └── snapshot/             # 每日快照写入
│       └── index.js
│
└── images/                   # 静态图片资源
    ├── tab/                  # tabBar 图标
    ├── icons/                # UI 图标
    └── themes/               # 主题装饰图（太阳/气泡等）
```

### app.json 配置

```json
{
  "pages": [
    "pages/index/index",
    "pages/watchlist/watchlist",
    "pages/settings/settings"
  ],
  "subpackages": [
    {
      "root": "subpackages/review",
      "name": "review",
      "pages": [
        "pages/sector/sector",
        "pages/history/history"
      ]
    },
    {
      "root": "subpackages/social",
      "name": "social",
      "pages": [
        "pages/invite/invite",
        "pages/poster/poster"
      ]
    }
  ],
  "preloadRule": {
    "pages/index/index": {
      "network": "all",
      "packages": ["review"]
    }
  },
  "window": {
    "navigationBarTitleText": "波段沙滩监控",
    "navigationBarBackgroundColor": "#87CEEB",
    "navigationBarTextStyle": "white",
    "backgroundColor": "#E8F4FD",
    "enablePullDownRefresh": true
  },
  "tabBar": {
    "color": "#999999",
    "selectedColor": "#1FA55A",
    "list": [
      {
        "pagePath": "pages/index/index",
        "text": "沙滩",
        "iconPath": "images/tab/home.png",
        "selectedIconPath": "images/tab/home-active.png"
      },
      {
        "pagePath": "pages/watchlist/watchlist",
        "text": "自选",
        "iconPath": "images/tab/stocks.png",
        "selectedIconPath": "images/tab/stocks-active.png"
      },
      {
        "pagePath": "pages/settings/settings",
        "text": "设置",
        "iconPath": "images/tab/settings.png",
        "selectedIconPath": "images/tab/settings-active.png"
      }
    ]
  },
  "cloud": true,
  "sitemapLocation": "sitemap.json",
  "style": "v2"
}
```

---

## 三、前端架构详解

### 3.1 页面职责划分

| 页面 | 功能 | 数据来源 | 刷新策略 |
|------|------|----------|----------|
| pages/index | 温度仪表 + 8 信号 + 11 指数 + 战法/风控 | 云函数 query | onShow 刷新 + 60s 定时 |
| pages/watchlist | 自选股列表 + 搜索 + 添加/删除 | 云函数 query + 本地存储 | onShow 刷新 |
| pages/settings | 主题切换 + 数据源说明 + 分享入口 | 本地存储 | 无网络请求 |
| subpackages/review/sector | 4 榜单 + 走势图 | 云函数 query | onShow 刷新 |
| subpackages/review/history | 历史快照时间线 | 云函数 snapshot | onShow 刷新 |

### 3.2 组件设计

**temp-gauge（温度仪表盘）**
- Properties: `temperature` (Number), `status` (String: 'cold'|'warm'|'hot')
- 功能：进度条 + 温和区间标记 + 判定文字 + 动画
- 小程序适配：用 WXSS animation 替代 SVG 海浪/气泡动画

**signal-panel（8 维信号面板）**
- Properties: `signals` (Array<{id, name, status}>)
- Events: `bind:toggle` — 用户手动切换信号状态
- 功能：8 个信号条，可点击循环切换 wait→buy→sell
- 自动判断逻辑在 `utils/signals.js` 中，组件只负责渲染

**index-list（多市场指数列表）**
- Properties: `indices` (Array<{key, name, market, price, changePct}>)
- 功能：按 A 股/港股/美股三组横排展示
- 涨跌幅自动着色（红涨绿跌）

**search-bar（股票搜索栏）**
- Properties: `pool` (Array<{code, name}>)
- Events: `bind:select` — 选中股票时触发
- 功能：输入框防抖搜索，最多显示 12 条结果
- 5534 只股票池存储在云 DB，云函数按关键词模糊查询

### 3.3 状态管理

采用 `globalData` + 页面 `setData` 的轻量方案：

```javascript
// app.js
App({
  globalData: {
    theme: 'day',           // 'day' | 'night'
    marketData: null,       // 最新市场数据缓存
    watchlist: [],          // 自选股代码数组
    lastUpdate: null,       // 最后更新时间
  },

  onLaunch() {
    // 恢复主题
    const theme = wx.getStorageSync('bw_theme') || 'day';
    this.globalData.theme = theme;

    // 恢复自选股
    const watchlist = wx.getStorageSync('bw_watchlist') || ['600519', '000858', '300750'];
    this.globalData.watchlist = watchlist;

    // 初始化云开发
    wx.cloud.init({ env: 'your-env-id' });
  },
});
```

### 3.4 主题系统适配

Web 版使用 CSS 变量，小程序改用 class 切换：

```css
/* app.wxss — 全局主题色 */

/* 白天：热带沙滩 */
.theme-day {
  --bg-primary: #E8F4FD;
  --bg-card: #FFFFFF;
  --text-primary: #1A1A2E;
  --text-secondary: #5F5E5A;
  --accent: #1FA55A;
  --coral: #FF6B6B;
  --border: rgba(0,0,0,0.08);
}

/* 夜间：深海潜水 */
.theme-night {
  --bg-primary: #0A0E27;
  --bg-card: #141B3D;
  --text-primary: #E8F4FD;
  --text-secondary: #7EB8C9;
  --accent: #7EF2E8;
  --coral: #FF6B6B;
  --border: rgba(126,242,232,0.12);
}

/* 小程序不支持 CSS 变量，需在每个组件内复制完整色值 */
/* 实际实现：用 page-level class + 各组件内 .theme-day/.theme-night 覆盖 */
```

---

## 四、后端云开发架构

### 4.1 云函数设计

**fetch（定时数据抓取）**

```javascript
// cloudfunctions/fetch/index.js
const cloud = require('wx-server-sdk');
const axios = require('axios');

cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });
const db = cloud.database();

// 新浪 hq 实时行情
async function fetchSinaHq(codes) {
  const url = `https://hq.sinajs.cn/list=${codes.join(',')}`;
  const res = await axios.get(url, {
    headers: { Referer: 'https://finance.sina.com.cn' },
    responseType: 'arraybuffer',
  });
  // GBK 解码 + 按市场格式解析
  // ... (移植自 fetch_market_data.py 的 parse_hq_value 逻辑)
}

// AKShare 板块资金流（通过 HTTP 代理调用 Python 服务）
async function fetchSectorFlow() {
  // 方案 1: 在云函数中用 Node.js 重写 AKShare 调用逻辑
  // 方案 2: 部署独立 Python 微服务，云函数通过 HTTP 调用
  // MVP 推荐方案 2：复用现有 fetch_market_data.py，部署为云容器
}

exports.main = async (event, context) => {
  try {
    // 1. 抓取实时行情
    const indices = await fetchSinaHq(INDEX_CODES);

    // 2. 抓取涨跌家数（通过 Python 微服务）
    const breadth = await fetchBreadth();

    // 3. 抓取板块资金流
    const sectors = await fetchSectorFlow();

    // 4. 计算温度
    const temperature = (breadth.up - breadth.down) / breadth.down;

    // 5. 写入云数据库（upsert）
    await db.collection('market_data').doc('latest').set({
      data: {
        indices, breadth, sectors, temperature,
        timestamp: new Date(),
        source: 'sina-hq + akshare',
      },
    });

    return { success: true, temperature };
  } catch (err) {
    console.error('fetch error:', err);
    return { success: false, error: err.message };
  }
};
```

**定时触发器配置**

```json
// cloudfunctions/fetch/config.json
{
  "triggers": [
    {
      "name": "tradingHours",
      "type": "timer",
      "config": "0 */1 9-15 * * MON-FRI *"
    },
    {
      "name": "preMarket",
      "type": "timer",
      "config": "0 0 9 * * MON-FRI *"
    },
    {
      "name": "postMarket",
      "type": "timer",
      "config": "0 30 15 * * MON-FRI *"
    }
  ]
}
```

**query（按需查询 + 缓存）**

```javascript
// cloudfunctions/query/index.js
exports.main = async (event, context) => {
  const { action, keyword, codes } = event;
  const db = cloud.database();

  if (action === 'market') {
    // 查缓存
    const cached = await db.collection('market_data').doc('latest').get();
    const age = Date.now() - new Date(cached.data.timestamp).getTime();

    if (age < 60000) {
      // 缓存有效（< 60s）
      return { success: true, data: cached.data, cached: true };
    }

    // 缓存过期，触发异步刷新 + 返回旧数据
    cloud.callFunction({ name: 'fetch', type: 'async' });
    return { success: true, data: cached.data, cached: true, stale: true };
  }

  if (action === 'search') {
    // 股票搜索：从 stock_pool 集合模糊查询
    const res = await db.collection('stock_pool')
      .where(db.command.or([
        { code: db.RegExp({ regexp: keyword, options: 'i' }) },
        { name: db.RegExp({ regexp: keyword, options: 'i' }) },
      ]))
      .limit(12)
      .get();
    return { success: true, data: res.data };
  }

  if (action === 'quotes') {
    // 自选股实时行情
    const res = await db.collection('stock_pool')
      .where({ code: db.command.in(codes) })
      .get();
    return { success: true, data: res.data };
  }
};
```

### 4.2 云数据库集合设计

| 集合名 | 文档结构 | 用途 |
|--------|----------|------|
| `market_data` | `{ _id: 'latest', indices, breadth, sectors, temperature, timestamp }` | 实时市场数据缓存 |
| `stock_pool` | `{ _id, code, name, price, changePct, market }` | 5534 只全 A 股票池 |
| `daily_snapshots` | `{ _id, date, up, down, flat, temperature, topIn[], topOut[] }` | 每日温度快照（最多 10 条） |
| `subscriptions` | `{ _id, openid, tmplId, status }` | 订阅消息授权记录 |

### 4.3 AKShare 部署方案

AKShare 是 Python 库，无法直接在 Node.js 云函数中运行。两个方案：

**方案 A（MVP 推荐）：Python 微服务 + 云函数代理**
- 将现有 `fetch_market_data.py` 部署为独立 Python 服务（云容器/轻量服务器）
- 云函数 `fetch` 通过 HTTP 调用该服务获取 AKShare 数据
- 新浪 hq 接口直接在云函数中用 axios 调用

**方案 B：纯 Node.js 重写**
- 用 `axios` + `cheerio` 重写 AKShare 的数据抓取逻辑
- 涨跌家数：直接请求新浪全 A 接口，自行统计
- 板块资金流：请求东方财富 API（需测试可用性）
- 延迟较高，但完全无需额外服务

---

## 五、关键迁移对照表

| Web 版技术 | 小程序替代 | 迁移难度 | 说明 |
|------------|-----------|----------|------|
| `fetch('data.json')` | `wx.cloud.callFunction('query')` | 中 | 需搭建云函数 + 云 DB |
| `localStorage` | `wx.setStorageSync` | 低 | API 直接对应 |
| `getElementById` + DOM 操作 | `setData()` 数据绑定 | 高 | 全部重写渲染逻辑 |
| CSS 变量 `var(--coral)` | WXSS class 切换 | 中 | 需复制色值到每个组件 |
| SVG 动画（海浪/气泡） | WXSS animation / Canvas | 高 | 视觉效果需重新实现 |
| SVG 折线图 | Canvas 2D API | 高 | 用 Canvas 重绘走势图 |
| `onclick` 内联事件 | `bindtap` + `data-*` | 低 | 批量替换 |
| `data_embedded.js` 回退 | 云 DB 缓存（不需要内嵌） | — | 小程序有网络，无需内嵌 |
| Python `fetch_market_data.py` | 云函数 + Python 微服务 | 中 | 拆分为云函数 + 后端服务 |
| 5534 只股票池（571KB JSON） | 云 DB `stock_pool` 集合 | 中 | 按需查询，不打包到小程序 |

---

## 六、性能优化要点

1. **setData 精简**：每次只传变化的数据，避免全量更新
   ```javascript
   // ❌ 全量更新
   this.setData({ marketData: newMarketData });
   // ✅ 精准更新
   this.setData({ 'marketData.temperature': temp });
   ```

2. **分包预加载**：用户在首页时预加载 review 分包
   ```json
   "preloadRule": {
     "pages/index/index": {
       "network": "all",
       "packages": ["review"]
     }
   }
   ```

3. **图片优化**：tabBar 图标用 PNG 压缩到 10KB 以内，装饰图用 CSS 替代

4. **云函数冷启动**：fetch 定时触发保持热实例，query 首次调用可能慢 1-2s

5. **缓存命中率**：cron 60s 预热，用户请求 95%+ 命中缓存

---

## 七、微信审核合规要点

### 7.1 必须配置

- [ ] **服务类目**：金融 → 证券行情（需金融资质或选择"工具→股票"）
- [ ] **隐私协议**：用户首次打开时弹出隐私授权弹窗
- [ ] **域名白名单**：云开发无需配置（走 `wx.cloud` 通道）
- [ ] **小程序名称**：不含"证券""投资"等敏感词（建议"波段沙滩"或"市场温度计"）

### 7.2 审核风险点

| 风险 | 应对 |
|------|------|
| 被判定为"荐股" | 页面明确标注"数据仅供参考，不构成投资建议" |
| 金融类目资质不足 | 选择"工具"类目，弱化"交易"相关文案 |
| 用户生成内容 | 自选股仅本地存储，不上传服务器，无 UGC 风险 |
| 数据来源合规 | 新浪/AKShare 均为公开数据接口，无需授权 |

### 7.3 必须声明

```json
// app.json
{
  "permission": {
    "scope.userLocation": {
      "desc": "不使用定位功能"
    }
  },
  "requiredPrivateInfos": []
}
```

> 本应用不涉及定位、相册、通讯录等敏感权限，审核风险低。

---

## 八、微信生态获客策略

### 8.1 分享裂变（Phase 2）

```javascript
// pages/index/index.js
onShareAppMessage() {
  const temp = this.data.temperature || '--';
  const status = this.data.tempStatus === 'warm' ? '温和上涨' : '观望';
  return {
    title: `今日市场温度 ${temp}，${status}，快来看看能不能下海冲浪`,
    path: '/pages/index/index',
    imageUrl: '/images/share/temperature-card.png',
  };
},

onShareTimeline() {
  return {
    title: `波段沙滩 · 今日温度 ${this.data.temperature || '--'}`,
    query: '',
    imageUrl: '/images/share/timeline.png',
  };
},
```

### 8.2 订阅消息（Phase 2）

- **盘前提醒**：每个交易日 9:00 推送昨日温度 + 今日预判
- **温度预警**：温度进入 1.30-1.50 温和区间时推送
- **模板 ID**：需在小程序后台申请订阅消息模板

### 8.3 小程序码（Phase 2）

- 生成带参数的小程序码，用于线下推广
- 参数标记来源渠道，便于追踪转化率

### 8.4 公众号联动（Phase 3）

- 绑定公众号，文章内嵌小程序卡片
- 公众号推送每日市场分析，引导打开小程序查看实时数据

---

## 九、MVP 分期计划

### Phase 1 — MVP（1 周提审）

**范围**：核心监控功能，砍掉板块复盘和社交分享

| 任务 | 工作量 |
|------|--------|
| 注册小程序 + 开通云开发 | 0.5 天 |
| app.json + tabBar + 主题框架 | 0.5 天 |
| pages/index（温度 + 信号 + 指数 + 战法） | 2 天 |
| pages/watchlist（自选股 + 搜索） | 1 天 |
| pages/settings（主题 + 关于） | 0.5 天 |
| 云函数 fetch + query + 云 DB | 1.5 天 |
| Python 微服务部署（AKShare 代理） | 0.5 天 |
| 联调 + 真机测试 + 提审 | 1 天 |
| **合计** | **7.5 天** |

### Phase 2 — 增长（上线后 2 周）

- 分包 A：板块复盘（4 榜单 + Canvas 走势图）
- 分包 B：社交分享（分享卡片 + 小程序码）
- 订阅消息（盘前提醒 + 温度预警）
- 历史快照时间线

### Phase 3 — 规模化（1 个月+）

- 用户登录 + 云端自选股同步
- 自定义战法规则
- 个股价格预警
- 港股/美股搜索扩展
- 公众号联动 + 视频号接入
- 广告位流量变现

---

## 十、技术风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| AKShare 接口不稳定 | 板块数据缺失 | 多源降级：东方财富 → 新浪 → 缓存旧数据 |
| 新浪 hq 防盗链升级 | 实时行情中断 | Referer 头模拟 + 备用 Tushare 源 |
| 云函数冷启动延迟 | 首次打开慢 1-2s | fetch 定时触发保持热实例 + 客户端 loading 态 |
| 小程序审核被拒 | 上线延迟 | 避免金融敏感词、标注免责声明、选"工具"类目 |
| 5534 只股票搜索慢 | 搜索体验差 | 云 DB 建索引 + 前端防抖 300ms + 限制 12 条 |
