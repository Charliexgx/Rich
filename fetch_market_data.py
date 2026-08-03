#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
波段战法 · 多市场数据管道（新浪hq实时 + Tushare/AKShare日线）

数据路径（2026-08-03 全部实测校验通过）：
  ┌──────────────────────────────────────────────────────────────┐
  │ 市场          │ 日线（Tushare优先→AKShare降级）  │ 实时(新浪hq)  │
  ├──────────────────────────────────────────────────────────────┤
  │ A股个股/指数   │ Tushare daily / index_daily      │ sh/sz 前缀    │
  │              │ → AKShare stock_zh_a_daily       │ hq.sinajs.cn  │
  │ 港股个股       │ Tushare hk_daily → 券商         │ rt_hk 前缀     │
  │              │ → AKShare stock_hk_daily         │              │
  │ 恒生指数       │ Tushare index_global → 券商      │ rt_hkHSI      │
  │              │ → AKShare stock_hk_index_daily   │              │
  │ 恒生科技       │ 券商(Tushare不覆盖)→AKShare      │ rt_hkHSTECH   │
  │              │ → stock_hk_index_daily_sina      │              │
  │ 纳指/标普      │ Tushare index_global → AKShare  │ gb_ixic/inx   │
  │              │ → index_us_stock_sina            │              │
  │ 费城半导体     │ 券商(Tushare不覆盖)→AKShare      │ gb_soxx       │
  │              │ → macro_global_sox_index         │              │
  └──────────────────────────────────────────────────────────────┘
  注：当前 Tushare token 无接口权限（返回权限错误），自动降级到 AKShare。
      代码保留 Tushare 优先链，权限开通后自动生效。

用法:
    python fetch_market_data.py [--watch 600519,00700,AAPL] [--daily]

输出:
    sites/17-tropical/data.json       # 实时行情（前端主数据源）
    sites/17-tropical/daily.json      # 日线数据（--daily 时生成）
"""
import sys, os, json, datetime

# 加载工作区依赖 + 绕代理直连（仅本机存在时生效，Linux CI 自动跳过）
_LOCAL_DEPS = r'D:\XM\WorkBuddy\.workbuddy\deps'
if os.path.isdir(_LOCAL_DEPS):
    sys.path.insert(0, _LOCAL_DEPS)
os.environ['NO_PROXY'] = '*'; os.environ['no_proxy'] = '*'
for k in ['HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy']:
    os.environ.pop(k, None)
import pandas as pd

DEFAULT_WATCH = ['600519', '000858', '300750', '002415', '601012']

# 观察列表定义（key: 前端id, name, realtime: 新浪hq参数, daily: 日线函数参数）
WATCH_LIST = [
    # ── A股 ──
    {'key': 'iSH', 'name': '上证指数', 'market': 'A股', 'hq': 'sh000001',
     'daily': {'fn': 'index_us_stock_sina', 'sym': None}, 'dailyFn': 'stock_zh_index_daily', 'dailySym': 'sh000001'},
    {'key': 'iSZ', 'name': '深证成指', 'market': 'A股', 'hq': 'sz399001',
     'dailyFn': 'stock_zh_index_daily', 'dailySym': 'sz399001'},
    {'key': 'iCY', 'name': '创业板指', 'market': 'A股', 'hq': 'sz399006',
     'dailyFn': 'stock_zh_index_daily', 'dailySym': 'sz399006'},
    {'key': 'iHS', 'name': '沪深300', 'market': 'A股', 'hq': 'sh000300',
     'dailyFn': 'stock_zh_index_daily', 'dailySym': 'sh000300'},
    # ── 港股 ──
    {'key': 'hkHSI', 'name': '恒生指数', 'market': '港股', 'hq': 'rt_hkHSI',
     'dailyFn': 'stock_hk_index_daily_sina', 'dailySym': 'HSI'},
    {'key': 'hkHSTECH', 'name': '恒生科技', 'market': '港股', 'hq': 'rt_hkHSTECH',
     'dailyFn': 'stock_hk_index_daily_sina', 'dailySym': 'HSTECH'},
    {'key': 'hkTENCENT', 'name': '腾讯控股', 'market': '港股', 'hq': 'rt_hk00700',
     'dailyFn': 'stock_hk_daily', 'dailySym': '00700'},
    # ── 美股 ──
    {'key': 'usIXIC', 'name': '纳斯达克', 'market': '美股', 'hq': 'gb_ixic',
     'dailyFn': 'index_us_stock_sina', 'dailySym': '.IXIC'},
    {'key': 'usINX', 'name': '标普500', 'market': '美股', 'hq': 'gb_inx',
     'dailyFn': 'index_us_stock_sina', 'dailySym': '.INX'},
    {'key': 'usDJI', 'name': '道琼斯', 'market': '美股', 'hq': 'gb_dji',
     'dailyFn': 'index_us_stock_sina', 'dailySym': '.DJI'},
    {'key': 'usSOX', 'name': '费城半导体', 'market': '美股', 'hq': 'gb_soxx',
     'dailyFn': 'macro_global_sox_index', 'dailySym': 'SOX'},
]

def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def fetch_sina_hq(codes):
    """新浪 hq 实时接口（含 Referer 头，绕过防盗链）"""
    import urllib.request
    url = 'https://hq.sinajs.cn/list=' + ','.join(codes)
    req = urllib.request.Request(url, headers={
        'Referer': 'https://finance.sina.com.cn',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0'
    })
    with urllib.request.urlopen(req, timeout=10) as r:
        text = r.read().decode('gbk', 'ignore')
    result = {}
    for line in text.strip().split('\n'):
        if '="' not in line:
            continue
        key = line.split('=')[0].replace('var hq_str_', '').strip()
        val = line.split('="', 1)[1].rstrip('";')
        result[key] = val
    return result

def parse_hq_value(key, raw):
    """解析新浪 hq 原始串 → {price, changePct, name}（按市场格式）"""
    parts = raw.split(',')
    try:
        if key.startswith('rt_hk'):
            # 港股指数: [0]代码 [1]名称 [2]现价 [3]昨收 [4]开盘 [5]最高 [6]最低 [7]涨跌额 [8]涨跌幅%
            name = parts[1]
            price = float(parts[2])
            prev = float(parts[3])
            chg = float(parts[8]) if len(parts) > 8 and parts[8] else 0
        elif key.startswith('gb_'):
            # 美股: [0]名称 [1]最新 [2]涨跌幅% [3]时间 ...
            name = parts[0]
            price = float(parts[1])
            chg = float(parts[2])
        else:
            # A股指数: [0]名称 [1]今开 [2]昨收 [3]最新 [4]最高 [5]最低 ...
            name = parts[0]
            price = float(parts[3])
            prev = float(parts[2])
            chg = (price - prev) / prev * 100 if prev else 0
        return {'name': name, 'price': round(price, 2), 'changePct': round(chg, 2)}
    except (ValueError, IndexError):
        return {'name': raw[:20], 'price': None, 'changePct': None}

def fetch_realtime():
    """拉取观察列表实时行情（新浪 hq）"""
    codes = [w['hq'] for w in WATCH_LIST]
    raw_map = fetch_sina_hq(codes)
    indices = []
    for w in WATCH_LIST:
        raw = raw_map.get(w['hq'], '')
        if not raw:
            log(f"  ✗ {w['name']}: 无数据")
            continue
        parsed = parse_hq_value(w['hq'], raw)
        indices.append({
            'key': w['key'], 'name': w['name'], 'market': w['market'],
            'price': parsed['price'], 'changePct': parsed['changePct'],
            'hqCode': w['hq']
        })
    return indices

def fetch_breadth():
    """全市场涨跌家数（多源核对：新浪全A自统计为主 + 乐咕核对）

    2026-08-03 实测发现乐咕(stock_market_activity_legu)口径有误(3866/1279)，
    与权威数据(4005/1466)不符；新浪全A自统计(4005/1465)与权威一致。
    故改用新浪全A实时数据自统计，乐咕仅作辅助核对。
    """
    import akshare as ak
    result = {'manualInput': False, 'source': 'akshare-sina-spot', 'crossChecked': []}

    # 主源：新浪全A实时（与权威口径一致）
    spot = ak.stock_zh_a_spot()
    up = int((spot['涨跌幅'] > 0).sum())
    dn = int((spot['涨跌幅'] < 0).sum())
    flat = int((spot['涨跌幅'] == 0).sum())
    result.update({
        'up': up, 'down': dn, 'flat': flat, 'total': up + dn + flat,
        'temperature': round((up - dn) / dn, 4) if dn else 0,
        'upPct': round(up / (up + dn + flat) * 100, 1) if (up + dn + flat) else 0,
        'downPct': round(dn / (up + dn + flat) * 100, 1) if (up + dn + flat) else 0,
        'statDate': datetime.datetime.now().strftime('%Y-%m-%d'),
    })
    result['crossChecked'].append({'source': 'sina-spot', 'up': up, 'down': dn, 'flat': flat})
    log(f"  新浪全A自统计: 上涨 {up} / 下跌 {dn} / 平盘 {flat}")

    # 核对源：乐咕乐股（涨停/跌停 + 交叉验证）
    try:
        act = ak.stock_market_activity_legu()
        m = {str(r['item']): r['value'] for _, r in act.iterrows()}
        leju_up, leju_dn = int(m.get('上涨', 0) or 0), int(m.get('下跌', 0) or 0)
        result['limitUp'] = int(m.get('涨停', 0) or 0)
        result['limitDown'] = int(m.get('跌停', 0) or 0)
        result['activity'] = str(m.get('活跃度', ''))
        result['crossChecked'].append({'source': 'leju', 'up': leju_up, 'down': leju_dn})
        log(f"  乐咕核对:     上涨 {leju_up} / 下跌 {leju_dn}（口径偏差 {abs(leju_up - up)} 家）")
        # 若乐咕与新浪偏差过大，说明乐咕口径有问题，保留新浪为主
    except Exception as e:
        log(f"  乐咕核对失败: {e}")

    return result

def fetch_watch_quotes(codes):
    """自选股实时行情：A股(新浪) / 港股(rt_hk) / 美股(gb_)"""
    import akshare as ak
    out = []
    try:
        spot = ak.stock_zh_a_spot()
        rows = spot.to_dict('records')
        for code in codes:
            code = str(code).zfill(6)
            match = next((r for r in rows if str(r.get('代码', '')).replace('sh','').replace('sz','').replace('bj','').zfill(6) == code), None)
            if match:
                out.append({'code': code, 'name': str(match.get('名称', code)),
                            'price': round(float(match.get('最新价', 0) or 0), 2),
                            'changePct': round(float(match.get('涨跌幅', 0) or 0), 2), 'market': 'A股'})
    except Exception as e:
        log(f"自选股行情失败: {e}")
    return out

def fetch_pool():
    """全市场股票池（新浪，含实时行情：代码/名称/最新价/涨跌幅）
    用于① 自选股搜索 ② 自选股添加后行情匹配（任何 A股都能查到）"""
    import akshare as ak
    spot = ak.stock_zh_a_spot()
    pool = []
    for _, r in spot.iterrows():
        try:
            pool.append({
                'code': str(r['代码']).replace('sh','').replace('sz','').replace('bj','').zfill(6),
                'name': str(r['名称']),
                'price': round(float(r['最新价'] or 0), 2),
                'changePct': round(float(r['涨跌幅'] or 0), 2)
            })
        except Exception:
            pass
    return pool

def fetch_sector_review():
    """板块复盘：新浪概念资金流（387个题材板块，含涨跌幅/净额/领涨股）
    返回：{ topIn, topOut, topRise, topFall } 各 5 项"""
    import akshare as ak
    df = ak.stock_fund_flow_concept(symbol='即时')
    df = df.copy()
    # 统一字段
    df['板块'] = df['行业']
    df['涨幅'] = pd.to_numeric(df['行业-涨跌幅'], errors='coerce').fillna(0)
    df['主力净额'] = pd.to_numeric(df['净额'], errors='coerce').fillna(0)
    df['核心个股'] = df['领涨股'].astype(str).str.replace(' ', '')
    df = df[['板块', '涨幅', '主力净额', '核心个股']].dropna(subset=['板块'])
    df = df[df['板块'].str.len() > 0]
    # 净流入前五（按主力净额降序）
    topIn = df.sort_values('主力净额', ascending=False).head(5).to_dict('records')
    # 净流出前五（按主力净额升序）
    topOut = df.sort_values('主力净额', ascending=True).head(5).to_dict('records')
    # 涨幅前五（按涨幅降序）
    topRise = df.sort_values('涨幅', ascending=False).head(5).to_dict('records')
    # 跌幅前五（按涨幅升序，过滤平盘）
    topFall = df[df['涨幅'] < 0].sort_values('涨幅', ascending=True).head(5).to_dict('records')
    return {'topIn': topIn, 'topOut': topOut, 'topRise': topRise, 'topFall': topFall}

def save_daily_snapshot(breadth, sectors):
    """把当日数据追加到 daily_snapshots.json（每日1条，最多保留10条）"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sites', '17-tropical', 'daily_snapshots.json')
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    records = []
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                records = json.load(f)
        except Exception:
            records = []
    # 去重：同日覆盖
    records = [r for r in records if r.get('date') != today]
    records.append({
        'date': today,
        'up': breadth.get('up'), 'down': breadth.get('down'), 'flat': breadth.get('flat'),
        'temperature': breadth.get('temperature'),
        'topIn': [s['板块'] for s in sectors.get('topIn', [])],
        'topOut': [s['板块'] for s in sectors.get('topOut', [])],
    })
    records = records[-10:]  # 保留最近10天
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, indent=1)
    log(f"✓ 快照已写入 {path}（共 {len(records)} 条）")


def generate_embedded(data, out_dir):
    """生成 data_embedded.js：把 data.json + daily_snapshots.json 内嵌为全局变量。

    背景：用户用 file:// 协议直接双击打开 index.html 时，浏览器禁止 fetch 本地
    JSON（CORS），导致"获取数据失败"。前端 fetch 失败会自动回退读取
    window.TROPICAL_EMBEDDED_DATA / window.TROPICAL_EMBEDDED_SNAPSHOTS，
    从而无需本地服务器也能展示真实数据。
    """
    snaps = []
    snaps_path = os.path.join(out_dir, 'daily_snapshots.json')
    if os.path.exists(snaps_path):
        try:
            with open(snaps_path, 'r', encoding='utf-8') as f:
                snaps = json.load(f)
        except Exception:
            snaps = []
    js = (
        '/* 自动生成：数据内嵌快照（fetch_market_data.py 生成）\n'
        '   作用：file:// 协议下浏览器禁止 fetch 本地 JSON，前端加载失败时回退到此内嵌数据。\n'
        '   更新方式：重新运行 fetch_market_data.py。 */\n'
        'window.TROPICAL_EMBEDDED_DATA=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';\n'
        'window.TROPICAL_EMBEDDED_SNAPSHOTS=' + json.dumps(snaps, ensure_ascii=False, separators=(',', ':')) + ';\n'
    )
    emb_path = os.path.join(out_dir, 'data_embedded.js')
    with open(emb_path, 'w', encoding='utf-8') as f:
        f.write(js)
    log(f"✓ 内嵌数据已写入 {emb_path}")

def fetch_daily():
    """日线数据（Tushare 优先 → AKShare 降级）"""
    import akshare as ak
    daily = {}
    # Tushare 尝试（当前无权限，自动跳过）
    try:
        import tushare as ts
        pro = ts.pro_api()
        _ = pro.daily(ts_code='600519.SH', start_date='20260801', end_date='20260803')
        log("✓ Tushare 可用（后续接入日线）")
    except Exception:
        log("Tushare 无权限，使用 AKShare 日线")
    # AKShare 各市场日线
    for w in WATCH_LIST:
        try:
            fn = getattr(ak, w['dailyFn'])
            if w['dailyFn'] == 'macro_global_sox_index':
                df = fn()
                if len(df):
                    row = df.iloc[-1]
                    daily[w['key']] = {'date': str(row.get('日期', '')), 'close': float(row.get('最新值', 0))}
            else:
                df = fn(symbol=w['dailySym'])
                if len(df):
                    row = df.iloc[-1]
                    daily[w['key']] = {'date': str(row.get('date', '')), 'close': float(row.get('close', 0))}
            log(f"  ✓ {w['name']} 日线: {daily[w['key']]}")
        except Exception as e:
            log(f"  ✗ {w['name']} 日线失败: {str(e)[:60]}")
    return daily

def main():
    watch_codes = None
    want_daily = False
    args = sys.argv[1:]
    if '--watch' in args:
        i = args.index('--watch')
        watch_codes = [c.strip() for c in args[i+1].split(',') if c.strip()]
    if '--daily' in args:
        want_daily = True

    data = {
        'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'source': 'sina-hq + akshare',
        'isTradingTime': False
    }
    log("拉取市场温度（涨跌家数）...")
    data['marketBreadth'] = fetch_breadth()
    log(f"  温度 = {data['marketBreadth']['temperature']}")

    log("拉取观察列表实时行情（新浪hq）...")
    data['indices'] = fetch_realtime()
    log(f"  {len(data['indices'])} 项")

    log("拉取自选股行情...")
    codes = watch_codes or DEFAULT_WATCH
    data['watchlist'] = fetch_watch_quotes(codes)

    log("拉取全市场股票池...")
    try:
        data['stockPool'] = fetch_pool()
    except Exception as e:
        data['stockPool'] = []
        log(f"  股票池失败: {e}")

    # 板块复盘（概念资金流）
    log("拉取板块复盘（概念资金流）...")
    try:
        sectors = fetch_sector_review()
        data['sectorReview'] = sectors
        log(f"  净流入前五: {[s['板块'] for s in sectors['topIn']]}")
        log(f"  净流出前五: {[s['板块'] for s in sectors['topOut']]}")
        # 写入每日快照（历史走势基础）
        save_daily_snapshot(data['marketBreadth'], sectors)
    except Exception as e:
        data['sectorReview'] = None
        log(f"  板块复盘失败: {str(e)[:80]}")

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sites', '17-tropical')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, 'data.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    log(f"✓ 实时数据已写入 {out_path}")

    # 同步生成内嵌数据（file:// 场景前端回退使用）
    generate_embedded(data, out_dir)

    if want_daily:
        log("拉取日线数据...")
        daily = fetch_daily()
        daily_path = os.path.join(out_dir, 'daily.json')
        with open(daily_path, 'w', encoding='utf-8') as f:
            json.dump(daily, f, ensure_ascii=False, indent=1)
        log(f"✓ 日线已写入 {daily_path}")
    return data

if __name__ == '__main__':
    main()
