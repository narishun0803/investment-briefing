#!/usr/bin/env python3
"""Investment briefing dashboard generator."""

import argparse
import calendar
import http.server
import json
import logging
import re
import shutil
import socket
import socketserver
import threading
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path

import feedparser
import pandas as pd
import yfinance as yf
from jinja2 import Environment, FileSystemLoader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))
DATA_DIR = Path(__file__).parent / "data"

# ── Market index tickers ──────────────────────────────────────────────────────

TICKERS = {
    "^N225": "日経225",
    "1306.T": "TOPIX (1306連動ETF)",
    "^GSPC": "S&P 500",
    "^IXIC": "NASDAQ",
    "^DJI": "ダウ",
    "JPY=X": "ドル円",
    "^TNX": "米10年債利回り",
    "CL=F": "WTI原油",
    "GC=F": "金",
}

TICKER_NOTES = {
    "1306.T": "TOPIX指数連動ETF",
}

SLOT_LABELS = {"morning": "朝", "noon": "昼", "evening": "夕", "night": "夜"}
SLOT_DESCS = {
    "morning": "米国市場結果・ADR・先物・夜間ニュース",
    "noon":    "日本前場総括・セクター騰落・決算速報",
    "evening": "日本大引け総括・主要決算・米国市場プレビュー",
    "night":   "米国寄り付き直前・経済指標・欧州市場",
}

SLOT_ORDER = {
    "morning": ["^GSPC", "^IXIC", "^DJI", "JPY=X", "^TNX", "CL=F", "GC=F", "^N225", "1306.T"],
    "noon":    ["^N225", "1306.T", "JPY=X", "^GSPC", "^IXIC", "^DJI", "^TNX", "CL=F", "GC=F"],
    "evening": ["^N225", "1306.T", "JPY=X", "^GSPC", "^IXIC", "^DJI", "^TNX", "CL=F", "GC=F"],
    "night":   ["^GSPC", "^IXIC", "^DJI", "JPY=X", "^TNX", "CL=F", "GC=F", "^N225", "1306.T"],
}

# ── Nikkei 225 contribution constants ─────────────────────────────────────────

# Approximate divisor as of 2026-05; update when TSE officially revises
NIKKEI_DIVISOR = 28.0

NIKKEI_FALLBACK = [
    {"code": "9983", "name": "ファーストリテイリング", "sector": "小売"},
    {"code": "8035", "name": "東京エレクトロン",      "sector": "半導体製造装置"},
    {"code": "9984", "name": "ソフトバンクG",          "sector": "通信"},
    {"code": "7203", "name": "トヨタ",                 "sector": "自動車"},
    {"code": "6758", "name": "ソニーG",                "sector": "電機"},
    {"code": "6861", "name": "キーエンス",             "sector": "電機"},
    {"code": "4063", "name": "信越化学",               "sector": "化学"},
    {"code": "6762", "name": "TDK",                    "sector": "電機"},
    {"code": "6857", "name": "アドバンテスト",         "sector": "電機"},
    {"code": "6098", "name": "リクルートHD",           "sector": "サービス"},
    {"code": "9433", "name": "KDDI",                   "sector": "通信"},
    {"code": "8058", "name": "三菱商事",               "sector": "商社"},
    {"code": "8031", "name": "三井物産",               "sector": "商社"},
    {"code": "8001", "name": "伊藤忠商事",             "sector": "商社"},
    {"code": "6501", "name": "日立製作所",             "sector": "電機"},
    {"code": "6981", "name": "村田製作所",             "sector": "電機"},
    {"code": "7974", "name": "任天堂",                 "sector": "電機"},
    {"code": "6954", "name": "ファナック",             "sector": "電機"},
    {"code": "7741", "name": "HOYA",                   "sector": "精密機器"},
    {"code": "6367", "name": "ダイキン",               "sector": "機械"},
    {"code": "4661", "name": "オリエンタルランド",     "sector": "サービス"},
    {"code": "4568", "name": "第一三共",               "sector": "医薬品"},
    {"code": "4502", "name": "武田薬品",               "sector": "医薬品"},
    {"code": "4523", "name": "エーザイ",               "sector": "医薬品"},
    {"code": "8306", "name": "三菱UFJ",                "sector": "銀行"},
    {"code": "8316", "name": "三井住友FG",             "sector": "銀行"},
    {"code": "8411", "name": "みずほFG",               "sector": "銀行"},
    {"code": "8766", "name": "東京海上HD",             "sector": "保険"},
    {"code": "7011", "name": "三菱重工",               "sector": "機械"},
    {"code": "7012", "name": "川崎重工",               "sector": "機械"},
]

# ── RSS feeds ─────────────────────────────────────────────────────────────────

RSS_FEEDS = [
    {"name": "ロイター日本ビジネス",  "url": "https://assets.wor.jp/rss/rdf/reuters/business.rdf"},
    {"name": "ロイター日本マーケット","url": "https://assets.wor.jp/rss/rdf/reuters/markets.rdf"},
    {"name": "ロイター日本トップ",    "url": "https://assets.wor.jp/rss/rdf/reuters/top.rdf"},
    {"name": "Yahoo!ファイナンス",    "url": "https://news.yahoo.co.jp/rss/categories/business.xml"},
    {"name": "日経マーケット",        "url": "https://www.nikkei.com/news/feed/?category=marketnews"},
    {"name": "ZUU online",            "url": "https://zuuonline.com/feed"},
    {"name": "Investing.com日本",     "url": "https://jp.investing.com/rss/news_25.rss"},
    {"name": "NHK経済",              "url": "https://www3.nhk.or.jp/rss/news/cat5.xml"},
]

INCLUDE_KEYWORDS = [
    "株価", "株式", "市場", "相場", "指数", "日経", "TOPIX", "ダウ", "ナスダック", "S&P",
    "為替", "ドル円", "円安", "円高", "金利", "利回り", "FOMC", "FRB", "日銀", "BOJ",
    "決算", "業績", "増益", "減益", "上方修正", "下方修正",
    "原油", "金価格", "商品市況", "経済指標", "GDP", "CPI", "雇用統計",
    "半導体", "AI関連", "銀行株", "自動車株",
    "M&A", "買収", "IPO", "配当", "自社株買い",
    "投資", "景気", "インフレ", "デフレ", "貿易", "輸出", "輸入",
    "東証", "NYSE", "Nasdaq", "先物", "オプション",
]

EXCLUDE_KEYWORDS = [
    "スポーツ", "芸能", "エンタメ", "訃報", "事故", "天気", "占い", "レシピ",
    "グルメ", "旅行", "ファッション", "コスメ", "恋愛", "婚活",
]

CATEGORY_RULES = {
    "market":   ["株価", "市場", "指数", "相場", "日経", "TOPIX", "ダウ", "ナスダック", "S&P",
                 "東証", "NYSE", "Nasdaq", "先物", "オプション", "株式"],
    "macro":    ["FOMC", "FRB", "日銀", "BOJ", "金利", "利回り", "為替", "ドル円",
                 "円安", "円高", "経済指標", "GDP", "CPI", "雇用統計", "インフレ",
                 "デフレ", "貿易", "輸出", "輸入", "景気"],
    "earnings": ["決算", "業績", "増益", "減益", "上方修正", "下方修正",
                 "M&A", "買収", "IPO", "配当", "自社株買い"],
}

SECTION_LABELS = {
    "market": "マーケット全般", "macro": "マクロ・金利",
    "earnings": "決算・個別銘柄", "other": "その他",
}

# yfinance exchange code → Google Finance exchange suffix
_EXCH_MAP = {"NYQ": "NYSE", "NMS": "NASDAQ", "NGM": "NASDAQ",
             "NCM": "NASDAQ", "NYSEArca": "NYSE", "PCX": "NYSE"}


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def detect_slot() -> str:
    h = datetime.now(JST).hour
    if 5  <= h < 9:  return "morning"
    if 11 <= h < 14: return "noon"
    if 17 <= h < 21: return "evening"
    if 22 <= h or h < 1: return "night"
    return "morning"


def _batch_prices(symbols: list[str]) -> dict[str, dict]:
    """Batch-fetch 2-day close via yf.download. Returns {sym: {price, prev_price, change, pct}}."""
    if not symbols:
        return {}
    try:
        raw = yf.download(
            symbols, period="2d", interval="1d",
            auto_adjust=True, progress=False, threads=True,
        )
        if raw.empty:
            return {}
        close = raw["Close"]
        # Normalize: single-sym string gives Series; list gives DataFrame
        if isinstance(close, pd.Series):
            close = close.to_frame(name=symbols[0])
        results: dict[str, dict] = {}
        for sym in symbols:
            if sym not in close.columns:
                continue
            col = close[sym].dropna()
            if col.empty:
                continue
            price = float(col.iloc[-1])
            prev  = float(col.iloc[-2]) if len(col) >= 2 else price
            chg   = price - prev
            pct   = (chg / prev * 100) if prev else 0.0
            results[sym] = {"price": price, "prev_price": prev, "change": chg, "pct": pct}
    except Exception as e:
        log.warning(f"  batch_prices error: {e}")
        return {}
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# Market index data
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_market_data(slot: str) -> list[dict]:
    order = SLOT_ORDER[slot]
    all_tickers = list(dict.fromkeys(order + list(TICKERS.keys())))
    results = []

    log.info("マーケットデータ取得中...")
    for sym in all_tickers:
        name = TICKERS.get(sym, sym)
        try:
            tk = yf.Ticker(sym)
            hist = tk.history(period="2d", interval="1d")
            if hist.empty:
                raise ValueError("データなし")

            price = float(hist["Close"].iloc[-1])
            prev  = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else price
            change = price - prev
            pct    = (change / prev * 100) if prev else 0.0

            if sym == "JPY=X":
                price_str, unit = f"{price:.2f}", "円"
            elif sym == "^TNX":
                price_str, unit = f"{price:.3f}", "%"
            elif sym in ("CL=F", "GC=F"):
                price_str, unit = f"{price:.2f}", "USD"
            elif sym == "^N225":
                price_str, unit = f"{price:,.2f}", "pt"
            elif sym == "1306.T":
                price_str, unit = f"{price:,.1f}", "円"
            else:
                price_str, unit = f"{price:,.2f}", ""

            direction = "up" if change > 0 else ("down" if change < 0 else "flat")
            log.info(f"  {name}: {price_str} {unit} ({pct:+.2f}%)")
            results.append({
                "symbol": sym, "name": name,
                "price": price_str, "unit": unit,
                "change": f"{change:+.2f}", "pct": f"{pct:+.2f}%",
                "direction": direction,
                "primary": sym in order[:5],
                "note": TICKER_NOTES.get(sym, ""),
                "_prev_price": prev,   # internal; used for S&P500 contribution calc
            })
        except Exception as e:
            log.warning(f"  {name} ({sym}) 取得失敗: {e}")
            results.append({
                "symbol": sym, "name": name,
                "price": "取得失敗", "unit": "",
                "change": "-", "pct": "-", "direction": "flat",
                "primary": sym in order[:5],
                "note": TICKER_NOTES.get(sym, ""),
                "_prev_price": 0.0,
            })

    order_idx = {s: i for i, s in enumerate(all_tickers)}
    results.sort(key=lambda x: order_idx.get(x["symbol"], 999))
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# Nikkei 225 individual contributions
# ═══════════════════════════════════════════════════════════════════════════════

def _load_nikkei_constituents() -> list[dict]:
    csv_path = DATA_DIR / "nikkei225_constituents.csv"
    if csv_path.exists():
        try:
            df = pd.read_csv(csv_path, dtype=str)
            stocks = df.to_dict("records")
            log.info(f"  日経225構成銘柄CSV読込: {len(stocks)}件")
            return stocks
        except Exception as e:
            log.warning(f"  CSV読込失敗、フォールバック使用: {e}")
    return NIKKEI_FALLBACK


def fetch_nikkei_contributions() -> dict:
    stocks = _load_nikkei_constituents()
    sym_map = {f"{s['code']}.T": s for s in stocks}
    symbols = list(sym_map.keys())

    log.info(f"日経225寄与度: {len(symbols)}銘柄を一括取得中...")
    prices = _batch_prices(symbols)

    results = []
    for sym, stock in sym_map.items():
        p = prices.get(sym)
        if p is None:
            log.warning(f"  スキップ: {stock['name']} ({sym})")
            continue
        contribution = p["change"] / NIKKEI_DIVISOR  # 寄与額(円) = 値動き / 除数
        results.append({
            "code":         stock["code"],
            "name":         stock["name"],
            "sector":       stock.get("sector", ""),
            "price":        f"{p['price']:,.0f}",
            "pct":          f"{p['pct']:+.2f}%",
            "contribution": contribution,
            "contrib_str":  f"{contribution:+.2f}",
            "direction":    "up" if contribution > 0 else ("down" if contribution < 0 else "flat"),
            "gf_url":       f"https://www.google.com/finance/quote/{stock['code']}:TYO",
        })

    results.sort(key=lambda x: x["contribution"], reverse=True)
    top_up   = [r for r in results if r["contribution"] > 0][:5]
    top_down = [r for r in reversed(results) if r["contribution"] < 0][:5]

    log.info(f"  日経225寄与度: 上昇{len(top_up)}件 / 下落{len(top_down)}件")
    return {"up": top_up, "down": top_down, "total": len(results)}


# ═══════════════════════════════════════════════════════════════════════════════
# S&P 500 individual contributions
# ═══════════════════════════════════════════════════════════════════════════════

_SP500_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def _load_sp500_constituents() -> list[dict]:
    import requests
    from io import StringIO

    csv_path = DATA_DIR / "sp500_constituents.csv"

    # Try Wikipedia with proper User-Agent to avoid 403
    try:
        log.info("  S&P500構成銘柄: Wikipedia取得中...")
        resp = requests.get(_SP500_WIKI_URL, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
        df = pd.read_html(StringIO(resp.text), attrs={"id": "constituents"})[0]
        DATA_DIR.mkdir(exist_ok=True)
        df.to_csv(csv_path, index=False)
        log.info(f"  S&P500構成銘柄: {len(df)}件取得・キャッシュ保存")
        return df.to_dict("records")
    except Exception as e:
        log.warning(f"  S&P500 Wikipedia取得失敗: {e}")

    # Fall back to CSV cache
    if csv_path.exists():
        try:
            df = pd.read_csv(csv_path)
            log.info(f"  S&P500構成銘柄: キャッシュから{len(df)}件読込")
            return df.to_dict("records")
        except Exception as e2:
            log.warning(f"  キャッシュ読込失敗: {e2}")
    return []


def _load_sp500_mcap_cache() -> dict:
    cache_path = DATA_DIR / "sp500_mcap_cache.json"
    if not cache_path.exists():
        return {}
    try:
        with open(cache_path) as f:
            cache = json.load(f)
        updated = datetime.fromisoformat(cache.get("updated", "2000-01-01T00:00:00+09:00"))
        if (datetime.now(JST) - updated).days < 7:
            return cache.get("stocks", {})
    except Exception:
        pass
    return {}


def _save_sp500_mcap_cache(stocks: dict):
    DATA_DIR.mkdir(exist_ok=True)
    cache_path = DATA_DIR / "sp500_mcap_cache.json"
    with open(cache_path, "w") as f:
        json.dump({"updated": datetime.now(JST).isoformat(), "stocks": stocks}, f)


def _fetch_one_mcap(sym: str) -> tuple[str, int, str]:
    """Fetch market cap and exchange for one symbol via fast_info."""
    try:
        fi = yf.Ticker(sym).fast_info
        cap  = int(getattr(fi, "market_cap",  0) or 0)
        exch = _EXCH_MAP.get(getattr(fi, "exchange", ""), "NASDAQ")
        return sym, cap, exch
    except Exception:
        return sym, 0, "NASDAQ"


def fetch_sp500_contributions(sp500_prev_close: float) -> dict:
    constituents = _load_sp500_constituents()
    if not constituents:
        log.warning("  S&P500構成銘柄なし、スキップ")
        return {"up": [], "down": [], "total": 0}

    # Build symbol → meta mapping from Wikipedia table
    sym_meta: dict[str, dict] = {}
    for row in constituents:
        sym  = str(row.get("Symbol") or row.get("symbol") or "").strip()
        if not sym or "." in sym:   # skip BRK.B style (yfinance uses BRK-B)
            sym = sym.replace(".", "-")
        if not sym:
            continue
        sym_meta[sym] = {
            "name":   str(row.get("Security") or row.get("security") or sym),
            "sector": str(row.get("GICS Sector") or row.get("sector") or ""),
        }

    all_syms = list(sym_meta.keys())

    # Load or refresh market cap cache
    mcap_cache = _load_sp500_mcap_cache()
    missing = [s for s in all_syms if s not in mcap_cache]

    if missing:
        log.info(f"  時価総額キャッシュミス: {len(missing)}銘柄を並列取得中 (max_workers=10)...")
        log.info("  ※初回は時間がかかります（結果はキャッシュされ次回は高速）")
        new_stocks: dict[str, dict] = {}
        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = {pool.submit(_fetch_one_mcap, sym): sym for sym in missing}
            for fut in as_completed(futures):
                sym, cap, exch = fut.result()
                new_stocks[sym] = {"cap": cap, "exchange": exch}
        # Merge with existing cache
        for sym, data in mcap_cache.items():
            if isinstance(data, dict):
                new_stocks.setdefault(sym, data)
            else:
                new_stocks.setdefault(sym, {"cap": int(data), "exchange": "NASDAQ"})
        mcap_cache = new_stocks
        _save_sp500_mcap_cache(mcap_cache)
        log.info(f"  時価総額キャッシュ保存: {len(mcap_cache)}銘柄")

    # Normalize cache values (handle both dict and legacy int formats)
    def _cap(sym: str) -> int:
        v = mcap_cache.get(sym, {})
        return v.get("cap", 0) if isinstance(v, dict) else int(v)

    def _exch(sym: str) -> str:
        v = mcap_cache.get(sym, {})
        return v.get("exchange", "NASDAQ") if isinstance(v, dict) else "NASDAQ"

    # Select top 50 by market cap
    ranked = sorted(all_syms, key=_cap, reverse=True)
    top50  = ranked[:50]
    total_cap = sum(_cap(s) for s in top50)

    log.info(f"  S&P500 上位50銘柄の価格を一括取得中...")
    prices = _batch_prices(top50)

    results = []
    for sym in top50:
        p = prices.get(sym)
        if p is None:
            log.warning(f"  スキップ: {sym}")
            continue
        cap    = _cap(sym)
        weight = cap / total_cap if total_cap else 0.0
        contrib = p["pct"] * weight * sp500_prev_close / 100 if sp500_prev_close else 0.0
        exch   = _exch(sym)
        results.append({
            "ticker":       sym,
            "name":         sym_meta[sym]["name"],
            "sector":       sym_meta[sym]["sector"],
            "price":        f"{p['price']:,.2f}",
            "pct":          f"{p['pct']:+.2f}%",
            "weight":       f"{weight * 100:.2f}%",
            "contribution": contrib,
            "contrib_str":  f"{contrib:+.2f}",
            "direction":    "up" if contrib > 0 else ("down" if contrib < 0 else "flat"),
            "gf_url":       f"https://www.google.com/finance/quote/{sym}:{exch}",
        })

    results.sort(key=lambda x: x["contribution"], reverse=True)
    top_up   = [r for r in results if r["contribution"] > 0][:5]
    top_down = [r for r in reversed(results) if r["contribution"] < 0][:5]

    log.info(f"  S&P500寄与度: 上昇{len(top_up)}件 / 下落{len(top_down)}件")
    return {"up": top_up, "down": top_down, "total": len(results)}


# ═══════════════════════════════════════════════════════════════════════════════
# News
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_date(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            ts = calendar.timegm(t)
            return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(JST)
    return None


def _contains_any(text: str, keywords: list[str]) -> bool:
    t = text.lower()
    return any(kw.lower() in t for kw in keywords)


def _classify_category(title: str, summary: str) -> str:
    combined = title + " " + summary
    for cat, keywords in CATEGORY_RULES.items():
        if _contains_any(combined, keywords):
            return cat
    return "other"


def _is_duplicate(title: str, seen: list[str], window: int = 20) -> bool:
    slug = re.sub(r"\s+", "", title)[:window]
    if slug in seen:
        return True
    seen.append(slug)
    return False


def fetch_news(slot: str) -> dict[str, list[dict]]:
    raw: list[dict] = []
    seen_slugs: list[str] = []

    for feed_info in RSS_FEEDS:
        try:
            log.info(f"RSS取得中: {feed_info['name']}")
            d = feedparser.parse(feed_info["url"])
            if d.bozo and not d.entries:
                raise ValueError(f"feedparser error: {d.bozo_exception}")

            count = 0
            for entry in d.entries[:10]:
                title = getattr(entry, "title", "").strip()
                if not title:
                    continue
                link        = getattr(entry, "link", "#")
                summary_raw = getattr(entry, "summary", "") or ""
                summary     = re.sub(r"<[^>]+>", "", summary_raw).strip()[:100]
                pub         = _parse_date(entry)
                pub_str     = pub.strftime("%m/%d %H:%M") if pub else "不明"
                combined    = title + " " + summary

                if _contains_any(combined, EXCLUDE_KEYWORDS):
                    continue
                if not _contains_any(combined, INCLUDE_KEYWORDS):
                    continue
                if _is_duplicate(title, seen_slugs):
                    continue

                raw.append({
                    "title":    title, "link": link,
                    "source":   feed_info["name"],
                    "published": pub_str,
                    "summary":  summary,
                    "pub_dt":   pub,
                    "category": _classify_category(title, summary),
                })
                count += 1

            log.info(f"  {count}件（フィルタ後）取得")
        except Exception as e:
            log.warning(f"  {feed_info['name']} RSS取得失敗: {e}")

    raw.sort(key=lambda x: x["pub_dt"] or datetime.min.replace(tzinfo=JST), reverse=True)
    for item in raw:
        item.pop("pub_dt", None)

    sections: dict[str, list[dict]] = {"market": [], "macro": [], "earnings": [], "other": []}
    for item in raw:
        cat = item["category"]
        if len(sections[cat]) < 10:
            sections[cat].append(item)

    total = sum(len(v) for v in sections.values())
    log.info(
        f"ニュース合計: {total}件 "
        f"(市場:{len(sections['market'])} マクロ:{len(sections['macro'])} "
        f"決算:{len(sections['earnings'])} その他:{len(sections['other'])})"
    )
    return sections


# ═══════════════════════════════════════════════════════════════════════════════
# Clipboard text builders
# ═══════════════════════════════════════════════════════════════════════════════

def _market_lines(market: list[dict]) -> list[str]:
    lines = ["【マーケットデータ】"]
    for m in market:
        if m["price"] == "取得失敗":
            lines.append(f"- {m['name']}: 取得失敗")
        else:
            unit = f" {m['unit']}" if m["unit"] else ""
            lines.append(f"- {m['name']}: {m['price']}{unit} ({m['pct']})")
    return lines


def _news_lines(news: dict[str, list[dict]], max_total: int = 20) -> list[str]:
    lines = ["【関連ニュース見出し】"]
    count = 0
    for cat_key in ("market", "macro", "earnings", "other"):
        for n in news.get(cat_key, []):
            if count >= max_total:
                break
            lines.append(f"- [{n['source']}] {n['title']} ({n['published']})")
            if n.get("summary"):
                lines.append(f"  概要: {n['summary']}")
            count += 1
    return lines


def _contrib_lines(nk: dict, sp: dict) -> list[str]:
    lines = ["【個別株の寄与度ランキング】"]

    lines.append("▼ 日経225 (上昇寄与TOP5)")
    for r in nk.get("up", []):
        lines.append(f"  +{r['contrib_str']}円  {r['name']}({r['code']})  {r['pct']}  [{r['sector']}]")
    lines.append("▼ 日経225 (下落寄与TOP5)")
    for r in nk.get("down", []):
        lines.append(f"  {r['contrib_str']}円  {r['name']}({r['code']})  {r['pct']}  [{r['sector']}]")

    lines.append("▼ S&P500 (上昇寄与TOP5)")
    for r in sp.get("up", []):
        lines.append(f"  +{r['contrib_str']}pt  {r['name']}({r['ticker']})  {r['pct']}  wt:{r['weight']}  [{r['sector']}]")
    lines.append("▼ S&P500 (下落寄与TOP5)")
    for r in sp.get("down", []):
        lines.append(f"  {r['contrib_str']}pt  {r['name']}({r['ticker']})  {r['pct']}  wt:{r['weight']}  [{r['sector']}]")

    return lines


def build_clipboard_overview(slot, market, news, nk_contrib, sp_contrib) -> str:
    now_str = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    lines = [
        f"以下は本日（{now_str}）の投資ブリーフィング情報です。",
        "",
        f"【時間帯】{SLOT_LABELS[slot]}（{SLOT_DESCS[slot]}）",
        "",
    ]
    lines += _market_lines(market)
    lines += [""]
    lines += _contrib_lines(nk_contrib, sp_contrib)
    lines += [""]
    lines += _news_lines(news, max_total=20)
    lines += [
        "",
        "【依頼内容】",
        "上記の指数の動きについて、ニュースの内容と紐付けて解説してください。",
        "特に以下を含めてください：",
        "1. 主要指数の動きの背景（特に大きく動いた指標）",
        "2. 相互の関連（例：金利↑とNASDAQ↓の関係）",
        "3. 注目すべきリスク要因",
        "4. 短期的に注視すべきポイント",
        "",
        "簡潔に、結論先出しでお願いします。",
    ]
    return "\n".join(lines)


def build_clipboard_deep(slot, market, news, nk_contrib, sp_contrib) -> str:
    lines = [
        "以下のマーケットデータとニュースを見て、",
        "特に動きが大きかった指標について、その背景をニュースから推測して解説してください。",
        "",
    ]
    lines += _market_lines(market)
    lines += [""]
    lines += _contrib_lines(nk_contrib, sp_contrib)
    lines += [""]
    lines += _news_lines(news, max_total=20)
    lines += [
        "",
        "【依頼内容】",
        "- 最も動きが大きかった指標トップ3を特定",
        "- それぞれの動きの背景にあるニュース・要因を推測",
        "- 「明確にニュースで説明できる動き」と「ニュースでは説明できない動き」を区別して提示",
    ]
    return "\n".join(lines)


def build_clipboard_risk(slot, market, news, nk_contrib, sp_contrib) -> str:
    lines = [
        "以下の情報から、投資判断において注視すべきリスクと注目点を抽出してください。",
        "",
    ]
    lines += _market_lines(market)
    lines += [""]
    lines += _contrib_lines(nk_contrib, sp_contrib)
    lines += [""]
    lines += _news_lines(news, max_total=20)
    lines += [
        "",
        "【依頼内容】",
        "- 短期的なリスク要因（今後1週間以内）",
        "- 中期的な注目イベント（決算・経済指標・政策発表など）",
        "- 個別銘柄で動きがあった主要企業",
        "- 私が見逃しそうなポイント",
    ]
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Local HTTP server + QR code
# ═══════════════════════════════════════════════════════════════════════════════

def _get_local_ip() -> str:
    """Return the machine's LAN IP (not 127.0.0.1)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _print_qr(url: str) -> None:
    try:
        import qrcode
        qr = qrcode.QRCode(border=2)
        qr.add_data(url)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
    except ImportError:
        log.info("  (pip3 install qrcode でQRコード表示可能)")


def serve_local(port: int = 8080) -> None:
    """Start HTTP server in output/ and display URL + QR code."""
    output_dir = Path(__file__).parent / "output"

    # Copy icon for PWA use
    icon_src = Path(__file__).parent / "icon_preview.png"
    if icon_src.exists():
        shutil.copy2(icon_src, output_dir / "icon.png")

    ip  = _get_local_ip()
    url = f"http://{ip}:{port}/briefing.html"

    log.info("=" * 52)
    log.info("  📱 スマホからアクセス")
    log.info(f"  URL: {url}")
    log.info("  (同じWiFiに接続している必要があります)")
    log.info("=" * 52)
    _print_qr(url)
    log.info("  Ctrl+C で停止")

    class _Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(output_dir), **kw)
        def log_message(self, fmt, *args):
            pass  # suppress per-request logs

    with socketserver.TCPServer(("", port), _Handler) as httpd:
        httpd.serve_forever()


# ═══════════════════════════════════════════════════════════════════════════════
# HTML rendering
# ═══════════════════════════════════════════════════════════════════════════════

def render_html(slot, market, news, nk_contrib, sp_contrib) -> str:
    base_dir = Path(__file__).parent
    env  = Environment(loader=FileSystemLoader(str(base_dir / "templates")))
    tmpl = env.get_template("briefing.html")
    now_str    = datetime.now(JST).strftime("%Y年%m月%d日 %H:%M JST")
    total_news = sum(len(v) for v in news.values())
    return tmpl.render(
        slot=slot,
        slot_label=SLOT_LABELS[slot],
        slot_desc=SLOT_DESCS[slot],
        market=market,
        news=news,
        section_labels=SECTION_LABELS,
        total_news=total_news,
        nk_contrib=nk_contrib,
        sp_contrib=sp_contrib,
        updated=now_str,
        clip_overview=build_clipboard_overview(slot, market, news, nk_contrib, sp_contrib),
        clip_deep=build_clipboard_deep(slot, market, news, nk_contrib, sp_contrib),
        clip_risk=build_clipboard_risk(slot, market, news, nk_contrib, sp_contrib),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="投資情報ブリーフィング生成")
    parser.add_argument("--slot", choices=["morning", "noon", "evening", "night"], help="時間帯を手動指定")
    parser.add_argument("--open",  action="store_true", dest="open_browser", help="生成後にブラウザで開く")
    parser.add_argument("--serve", action="store_true", help="生成後にHTTPサーバーを起動してスマホからアクセス可能にする")
    parser.add_argument("--port",  type=int, default=8080, help="--serve 時のポート番号 (default: 8080)")
    args = parser.parse_args()

    slot = args.slot or detect_slot()
    log.info(f"時間帯: {SLOT_LABELS[slot]} ({slot}) — {SLOT_DESCS[slot]}")

    import time
    t0 = time.time()

    market     = fetch_market_data(slot)
    sp500_prev = next((m["_prev_price"] for m in market if m["symbol"] == "^GSPC"), 0.0)

    news       = fetch_news(slot)
    nk_contrib = fetch_nikkei_contributions()
    sp_contrib = fetch_sp500_contributions(sp500_prev)

    log.info(f"データ取得完了: {time.time() - t0:.1f}秒")

    html     = render_html(slot, market, news, nk_contrib, sp_contrib)
    out_path = Path(__file__).parent / "output" / "briefing.html"
    out_path.write_text(html, encoding="utf-8")
    log.info(f"HTML出力: {out_path}")

    if args.open_browser:
        webbrowser.open(out_path.as_uri())
        log.info("ブラウザで開きました")

    if args.serve:
        serve_local(args.port)


if __name__ == "__main__":
    main()
