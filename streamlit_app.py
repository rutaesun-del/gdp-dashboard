import re
import os
import html
import sqlite3
import feedparser
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote
from playwright.sync_api import sync_playwright
from streamlit_autorefresh import st_autorefresh


st.set_page_config(page_title="뉴스 터미널", layout="wide")
st_autorefresh(interval=20000, key="refresh")

KST = timezone(timedelta(hours=9))
DB_PATH = "NEWS_TERMINAL_PLAYWRIGHT_FINAL.db"
KEEP_HOURS = 24
MAX_WORKERS = 6

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "ko-KR,ko;q=0.9",
}


POSITIVE = [
    "수주","계약","공급","양산","증설","투자","흑자","호실적","최초","최고","최대","역대","갱신",
    "상향","돌파","승인","성장","강세","급등","확대","협력","기대","호재","개선","수혜","신고가",
    "사상 최고","반등","회복","증가","확보","선정","채택","성과","호황","출시","개발","상승",
    "랠리","목표가 상향","실적 개선","턴어라운드","흑자전환","매출 증가","영업익 증가","재평가"
]

NEGATIVE = [
    "적자","감산","규제","소송","리콜","중단","악화","급락","하락","우려","부진","손실","취소",
    "철회","약세","압박","감소","실패","파업","제재","폭락","경고","쇼크","둔화","불확실",
    "위기","타격","하향","퇴출","논란","과징금","거래정지","압수수색"
]

BAD_WORDS = [
    "운세","별자리","책꽂이","포토","화보","갤러리","연예","배우","가수","드라마","영화",
    "맛집","여행","날씨","폭염","호우","태풍","사건","사고","살해","경찰","검찰","재판",
    "구속","채용","공모","공지","알림","유튜브","인스타그램","페이스북","트위터",
    "많이 본 뉴스","인기검색어","저작권","로그인","구독","전체보기","메뉴"
]

STOCK_WORDS = [
    "주식","증시","코스피","코스닥","상장","공시","투자","수주","계약","공급","양산","증설",
    "실적","매출","영업익","흑자","적자","목표가","증권","기관","외국인","시총","ETF",
    "반도체","AI","HBM","GPU","데이터센터","2차전지","배터리","전기차","자동차","조선",
    "원전","로봇","방산","바이오","제약","디스플레이","삼성전자","SK하이닉스","하이닉스",
    "엔비디아","현대차","기아","카카오","네이버","LG","한화","두산","셀트리온","에코프로",
    "포스코","TSMC","마이크론","OLED","D램","낸드"
]

COMPANY_RULES = {
    "삼성전자": ["삼성전자"],
    "SK하이닉스": ["SK하이닉스","하이닉스"],
    "엔비디아": ["엔비디아","NVIDIA","루빈","GPU"],
    "TSMC": ["TSMC"],
    "한미반도체": ["한미반도체","TC본더"],
    "삼성전기": ["삼성전기","FC-BGA"],
    "현대차": ["현대차","현대자동차"],
    "기아": ["기아"],
    "카카오": ["카카오"],
    "네이버": ["네이버","NAVER"],
    "LG에너지솔루션": ["LG에너지솔루션","LG엔솔"],
}

THEME_RULES = {
    "AI": ["AI","인공지능","GPU","엔비디아","데이터센터"],
    "반도체": ["반도체","HBM","파운드리","메모리","D램","DRAM","낸드"],
    "PCB": ["PCB","FC-BGA","기판","패키지기판"],
    "자동차": ["현대차","기아","전기차","자동차"],
    "2차전지": ["배터리","2차전지","전고체"],
    "조선": ["조선","LNG","선박"],
    "원전": ["원전","원자력"],
    "증시": ["코스피","코스닥","증시","ETF","상장","시총"],
}


def now():
    return datetime.now(KST).replace(tzinfo=None)


def clean(x):
    return re.sub(r"\s+", " ", str(x or "")).strip()


def norm_title(t):
    t = clean(t)
    t = re.sub(r"\[[^\]]+\]|\([^)]*\)", "", t)
    t = re.sub(r"[^가-힣A-Za-z0-9]", "", t)
    return t.lower()


def parse_dt(text):
    text = clean(text)

    try:
        s = text.replace("Z", "+00:00")
        if "T" in s:
            d = datetime.fromisoformat(s)
            if d.tzinfo:
                d = d.astimezone(KST)
            return d.replace(tzinfo=None)
    except:
        pass

    patterns = [
        r"(\d{4})[-.](\d{1,2})[-.](\d{1,2})[.\s]+(오전|오후)?\s*(\d{1,2}):(\d{2})",
        r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일\s*(오전|오후)?\s*(\d{1,2}):(\d{2})",
        r"(\d{2})[-.](\d{2})\s+(\d{1,2}):(\d{2})",
    ]

    for p in patterns:
        m = re.search(p, text)
        if not m:
            continue

        g = m.groups()

        if len(g) == 6:
            y, mo, da, ap, h, mi = g
        else:
            mo, da, h, mi = g
            y, ap = now().year, None

        h = int(h)
        if ap == "오후" and h < 12:
            h += 12
        if ap == "오전" and h == 12:
            h = 0

        return datetime(int(y), int(mo), int(da), h, int(mi))

    return None


def recent(d):
    if not d:
        return False
    n = now()
    return n - timedelta(hours=KEEP_HOURS) <= d <= n + timedelta(minutes=5)


def valid_title(t):
    t = clean(t)
    if len(t) < 8 or len(t) > 180:
        return False
    if any(w.lower() in t.lower() for w in BAD_WORDS):
        return False
    return True


def stock_related(t):
    low = t.lower()
    return any(w.lower() in low for w in STOCK_WORDS)


def sentiment(t):
    p = sum(w in t for w in POSITIVE)
    n = sum(w in t for w in NEGATIVE)
    if p > n:
        return "🔵 긍정"
    if n > p:
        return "🔴 부정"
    return "⚪ 중립"


def company(t):
    found = []
    for k, arr in COMPANY_RULES.items():
        if any(w.lower() in t.lower() for w in arr):
            found.append(k)
    return ", ".join(found) if found else "미분류"


def theme(t):
    found = []
    for k, arr in THEME_RULES.items():
        if any(w.lower() in t.lower() for w in arr):
            found.append(k)
    return ", ".join(found) if found else "기타"


def make_row(title, link, media, dt):
    title = clean(title)
    if not valid_title(title):
        return None
    if not recent(dt):
        return None

    return {
        "title": title,
        "display_title": title[:150] + "..." if len(title) > 150 else title,
        "sentiment": sentiment(title),
        "company": company(title),
        "theme": theme(title),
        "media": media,
        "display_dt": dt.strftime("%m-%d %H:%M"),
        "sort_ts": dt.timestamp(),
        "stock_related": 1 if stock_related(title) else 0,
        "dedupe_key": norm_title(title),
        "link": link,
        "inserted_at": now().isoformat(),
    }


def browser_collect(url, media, selectors, wait=2500):
    rows = []
    seen = set()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(locale="ko-KR")
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(wait)

            html_text = page.content()
            browser.close()

        soup = BeautifulSoup(html_text, "lxml")

        for selector in selectors:
            for item in soup.select(selector):
                a = item if item.name == "a" else item.select_one("a[href]")
                if not a:
                    continue

                title = clean(a.get_text(" ") or a.get("title"))
                href = a.get("href", "")

                if not href:
                    continue

                if href.startswith("//"):
                    link = "https:" + href
                elif href.startswith("http"):
                    link = href
                elif href.startswith("/"):
                    base = "/".join(url.split("/")[:3])
                    link = base + href
                else:
                    base = "/".join(url.split("/")[:3])
                    link = base + "/" + href

                key = norm_title(title)
                if not key or key in seen:
                    continue
                seen.add(key)

                block = item.get_text(" ")
                dt = parse_dt(block)

                if not dt:
                    dt = fetch_article_time(link)

                r = make_row(title, link, media, dt)
                if r:
                    rows.append(r)

    except Exception:
        pass

    return rows


def fetch_article_time(link):
    try:
        import requests
        r = requests.get(link, headers=HEADERS, timeout=5)
        r.encoding = r.apparent_encoding
        soup = BeautifulSoup(r.text, "lxml")

        candidates = []

        for attr in [
            {"property": "article:published_time"},
            {"property": "og:regDate"},
            {"name": "date"},
            {"name": "pubdate"},
            {"name": "publish-date"},
            {"itemprop": "datePublished"},
        ]:
            m = soup.find("meta", attr)
            if m and m.get("content"):
                candidates.append(m.get("content"))

        for sel in [
            ".media_end_head_info_datestamp_time",
            "span._ARTICLE_DATE_TIME",
            ".articleInfo .date",
            ".article_info .date",
            ".num_date",
            ".txt_date",
            ".txt-date",
            ".article-timestamp",
            ".registration",
            ".time_area",
            ".view_time",
            ".news_dates",
            ".dates",
            ".article_date",
            ".update-time",
            ".txt-time",
            ".date",
            ".time",
            "time",
        ]:
            for tag in soup.select(sel):
                if tag.get("datetime"):
                    candidates.append(tag.get("datetime"))
                candidates.append(tag.get_text(" "))

        for c in candidates:
            d = parse_dt(c)
            if recent(d):
                return d

    except Exception:
        return None

    return None


def rss_collect(media, url, limit=80):
    rows = []
    try:
        f = feedparser.parse(url)
        for e in f.entries[:limit]:
            title = clean(e.get("title", ""))
            link = e.get("link", "")
            if " - " in title and media.startswith("구글"):
                title = clean(title.rsplit(" - ", 1)[0])

            d = None
            try:
                raw = e.get("published") or e.get("updated")
                if raw:
                    d = parsedate_to_datetime(raw)
                    if d.tzinfo:
                        d = d.astimezone(KST)
                    d = d.replace(tzinfo=None)
            except:
                d = None

            if not d:
                d = fetch_article_time(link)

            r = make_row(title, link, media, d)
            if r:
                rows.append(r)
    except:
        pass
    return rows


def google_rss(q):
    return f"https://news.google.com/rss/search?q={quote(q)}&hl=ko&gl=KR&ceid=KR:ko"


def collect_all():
    tasks = [
        lambda: browser_collect(
            "https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258",
            "네이버금융",
            ["dl.newsList", "dt.articleSubject", "dd.articleSubject", "a[href*='news_read.naver']"],
        ),
        lambda: browser_collect(
            "https://news.naver.com/main/list.naver?mode=LSD&mid=shm&sid1=101",
            "네이버뉴스",
            ["ul.type06_headline li", "ul.type06 li"],
        ),
        lambda: browser_collect(
            "https://news.daum.net/finance",
            "다음금융",
            ["ul.list_news2 li", "ul.list_news li", "a[href*='v.daum.net']"],
        ),
        lambda: browser_collect(
            "https://finance.daum.net/news",
            "다음금융",
            ["a[href*='v.daum.net']", "a[href*='/news/']"],
        ),

        lambda: rss_collect("한국경제", "https://www.hankyung.com/feed/all-news"),
        lambda: rss_collect("한국경제-증권", "https://www.hankyung.com/feed/finance"),
        lambda: rss_collect("매일경제", "https://www.mk.co.kr/rss/30000001/"),
        lambda: rss_collect("구글뉴스-경제", "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko"),
        lambda: rss_collect("뉴시스", google_rss("site:newsis.com 경제 OR 증시 OR 기업 OR 반도체")),
        lambda: rss_collect("이데일리", google_rss("site:edaily.co.kr 증시 OR 주식 OR 반도체 OR 기업")),
        lambda: rss_collect("머니투데이", google_rss("site:mt.co.kr 증시 OR 주식 OR 반도체 OR 기업")),
        lambda: rss_collect("서울경제", google_rss("site:sedaily.com 증시 OR 주식 OR 반도체 OR 기업")),
        lambda: rss_collect("아시아경제", google_rss("site:asiae.co.kr 증시 OR 주식 OR 반도체 OR 기업")),
        lambda: rss_collect("연합뉴스", google_rss("site:yna.co.kr 경제 OR 증시 OR 기업 OR 반도체")),
        lambda: rss_collect("뉴스1", google_rss("site:news1.kr 경제 OR 증시 OR 기업 OR 반도체")),
        lambda: rss_collect("전자신문", google_rss("site:etnews.com 반도체 OR AI OR 기업 OR 증시")),
        lambda: rss_collect("ZDNet", google_rss("site:zdnet.co.kr 반도체 OR AI OR 기업 OR 증시")),
        lambda: rss_collect("디지털데일리", google_rss("site:ddaily.co.kr 반도체 OR AI OR 기업 OR 증시")),
        lambda: rss_collect("조선비즈", google_rss("site:biz.chosun.com 증시 OR 주식 OR 반도체 OR 기업")),
    ]

    out = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(t) for t in tasks]
        for f in as_completed(futures):
            try:
                out.extend(f.result())
            except:
                pass
    return out


def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""
    CREATE TABLE IF NOT EXISTS news(
        title TEXT,
        display_title TEXT,
        sentiment TEXT,
        company TEXT,
        theme TEXT,
        media TEXT,
        display_dt TEXT,
        sort_ts REAL,
        stock_related INTEGER,
        dedupe_key TEXT,
        link TEXT UNIQUE,
        inserted_at TEXT
    )
    """)
    con.commit()
    con.close()


def save(rows):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    for r in rows:
        cur.execute("""
        INSERT INTO news VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(link) DO UPDATE SET
            title=excluded.title,
            display_title=excluded.display_title,
            sentiment=excluded.sentiment,
            company=excluded.company,
            theme=excluded.theme,
            media=excluded.media,
            display_dt=excluded.display_dt,
            sort_ts=excluded.sort_ts,
            stock_related=excluded.stock_related,
            dedupe_key=excluded.dedupe_key,
            inserted_at=excluded.inserted_at
        """, (
            r["title"], r["display_title"], r["sentiment"], r["company"], r["theme"],
            r["media"], r["display_dt"], r["sort_ts"], r["stock_related"],
            r["dedupe_key"], r["link"], r["inserted_at"]
        ))

    con.commit()
    con.close()


def load():
    con = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM news", con)
    con.close()

    if df.empty:
        return df

    cutoff = (now() - timedelta(hours=KEEP_HOURS)).timestamp()
    df["sort_ts"] = pd.to_numeric(df["sort_ts"], errors="coerce")
    df = df[df["sort_ts"] >= cutoff]
    df = (
        df.sort_values("sort_ts", ascending=False)
        .drop_duplicates("dedupe_key", keep="first")
        .reset_index(drop=True)
    )
    return df


@st.cache_data(ttl=20)
def refresh():
    init_db()
    save(collect_all())
    return load()


st.title("📰 뉴스 터미널")
st.caption("20초 자동갱신 | Playwright 브라우저 수집 | 원문/RSS 절대시간 기준 | 최근 24시간 | 중복 제거")

if st.button("DB 완전 초기화 / 강제 새로고침"):
    st.cache_data.clear()
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    st.rerun()

df = refresh()

if df.empty:
    st.warning("뉴스가 없습니다. 첫 실행이면 20~40초 기다린 뒤 새로고침하세요.")
    st.stop()

c0, c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 1, 2])

with c0:
    stock_filter = st.selectbox("범위", ["전체", "주식관련만"])
with c1:
    sent_filter = st.selectbox("감성", ["전체", "🔵 긍정", "⚪ 중립", "🔴 부정"])
with c2:
    comp_filter = st.selectbox("회사명", ["전체"] + sorted(df["company"].unique()))
with c3:
    theme_filter = st.selectbox("테마", ["전체"] + sorted(df["theme"].unique()))
with c4:
    media_filter = st.selectbox("매체", ["전체"] + sorted(df["media"].unique()))
with c5:
    search = st.text_input("검색")

f = df.copy()

if stock_filter == "주식관련만":
    f = f[f["stock_related"] == 1]
if sent_filter != "전체":
    f = f[f["sentiment"] == sent_filter]
if comp_filter != "전체":
    f = f[f["company"] == comp_filter]
if theme_filter != "전체":
    f = f[f["theme"] == theme_filter]
if media_filter != "전체":
    f = f[f["media"] == media_filter]
if search:
    f = f[
        f["title"].str.contains(search, case=False, na=False)
        | f["company"].str.contains(search, case=False, na=False)
        | f["theme"].str.contains(search, case=False, na=False)
    ]

f = f.sort_values("sort_ts", ascending=False).reset_index(drop=True)

st.subheader(f"전체 뉴스 {len(f)}개")

with st.expander("매체별 수집 개수 확인"):
    st.dataframe(
        df.groupby("media").size().reset_index(name="개수").sort_values("개수", ascending=False),
        use_container_width=True,
        hide_index=True,
    )

rows = ""
for _, r in f.head(1500).iterrows():
    rows += f"""
    <tr>
        <td class="title"><a href="{html.escape(r['link'])}" target="_blank">{html.escape(r['display_title'])}</a></td>
        <td>{html.escape(r['sentiment'])}</td>
        <td>{html.escape(r['company'])}</td>
        <td>{html.escape(r['theme'])}</td>
        <td>{html.escape(r['media'])}</td>
        <td>{html.escape(r['display_dt'])}</td>
    </tr>
    """

components.html(f"""
<style>
table {{
    width:100%;
    border-collapse:collapse;
    font-size:12.5px;
    table-layout:fixed;
}}
th {{
    background:#f1f3f5;
    padding:7px;
    border-bottom:1px solid #ddd;
    text-align:left;
}}
td {{
    padding:5px 6px;
    border-bottom:1px solid #eee;
    white-space:nowrap;
    overflow:hidden;
    text-overflow:ellipsis;
}}
tr:hover {{ background:#f8f9fa; }}
.title {{ width:70%; font-weight:600; }}
a {{ color:#005bac; text-decoration:none; }}
a:hover {{ text-decoration:underline; }}
</style>

<table>
<thead>
<tr>
<th class="title">제목</th>
<th>감성</th>
<th>회사명</th>
<th>테마</th>
<th>매체</th>
<th>일자</th>
</tr>
</thead>
<tbody>{rows}</tbody>
</table>
""", height=850, scrolling=True)
