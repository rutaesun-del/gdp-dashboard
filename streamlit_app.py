import re
import html
import os
import sqlite3
import requests
import feedparser
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed
from streamlit_autorefresh import st_autorefresh


# =========================================================
# 기본 설정
# =========================================================

st.set_page_config(page_title="뉴스 터미널", layout="wide")
st_autorefresh(interval=10000, key="refresh")

KST = timezone(timedelta(hours=9))

DB_PATH = "news_terminal_last_final.db"
KEEP_HOURS = 24

TIMEOUT = 5
MAX_WORKERS = 10

NAVER_FINANCE_PAGES = 10
NAVER_NEWS_PAGES = 3

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
}


def google_rss(q):
    return f"https://news.google.com/rss/search?q={quote(q)}&hl=ko&gl=KR&ceid=KR:ko"


# =========================================================
# 뉴스 소스
# =========================================================

SOURCES = [
    {
        "name": "네이버금융",
        "type": "naver_finance",
        "url": "https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258",
        "base": "https://finance.naver.com",
        "encoding": "euc-kr",
    },
    {
        "name": "네이버뉴스",
        "type": "naver_news",
        "url": "https://news.naver.com/main/list.naver?mode=LSD&mid=shm&sid1=101",
        "base": "https://news.naver.com",
        "encoding": "euc-kr",
    },
    {
        "name": "다음금융",
        "type": "daum_finance",
        "url": "https://finance.daum.net/news",
        "base": "https://finance.daum.net",
        "encoding": "utf-8",
    },

    {"name": "한국경제", "type": "rss", "url": "https://www.hankyung.com/feed/all-news"},
    {"name": "한국경제-증권", "type": "rss", "url": "https://www.hankyung.com/feed/finance"},
    {"name": "매일경제", "type": "rss", "url": "https://www.mk.co.kr/rss/30000001/"},
    {"name": "구글뉴스-경제", "type": "rss", "url": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko"},

    {"name": "서울경제", "type": "generic", "url": "https://www.sedaily.com/NewsList/GA", "base": "https://www.sedaily.com", "encoding": "utf-8", "allow": ["/NewsView/"]},
    {"name": "이데일리", "type": "generic", "url": "https://www.edaily.co.kr/News/Stock", "base": "https://www.edaily.co.kr", "encoding": "utf-8", "allow": ["/News/Read"]},
    {"name": "머니투데이", "type": "generic", "url": "https://news.mt.co.kr/newsList.html?pDepth1=stock", "base": "https://news.mt.co.kr", "encoding": "utf-8", "allow": ["/mtview.php", "/newsView.html"]},
    {"name": "아시아경제", "type": "generic", "url": "https://www.asiae.co.kr/news/list.htm?sec=eco99", "base": "https://www.asiae.co.kr", "encoding": "utf-8", "allow": ["/article/"]},
    {"name": "파이낸셜뉴스", "type": "generic", "url": "https://www.fnnews.com/section/002000000", "base": "https://www.fnnews.com", "encoding": "utf-8", "allow": ["/news/"]},
    {"name": "조선비즈", "type": "generic", "url": "https://biz.chosun.com/stock/", "base": "https://biz.chosun.com", "encoding": "utf-8", "allow": ["/stock/", "/industry/", "/it-science/"]},
    {"name": "전자신문", "type": "generic", "url": "https://www.etnews.com/news/section.html?id1=20", "base": "https://www.etnews.com", "encoding": "utf-8", "allow": ["/news/article.html"]},
    {"name": "ZDNet", "type": "generic", "url": "https://zdnet.co.kr/news/", "base": "https://zdnet.co.kr", "encoding": "utf-8", "allow": ["/view/"]},
    {"name": "디지털데일리", "type": "generic", "url": "https://www.ddaily.co.kr/", "base": "https://www.ddaily.co.kr", "encoding": "utf-8", "allow": ["/page/view/"]},
    {"name": "연합뉴스", "type": "generic", "url": "https://www.yna.co.kr/economy/all", "base": "https://www.yna.co.kr", "encoding": "utf-8", "allow": ["/view/"]},
    {"name": "뉴스1", "type": "generic", "url": "https://www.news1.kr/economy", "base": "https://www.news1.kr", "encoding": "utf-8", "allow": ["/articles/"]},
    {"name": "한국일보", "type": "generic", "url": "https://www.hankookilbo.com/News/Economy", "base": "https://www.hankookilbo.com", "encoding": "utf-8", "allow": ["/News/Read"]},

    {"name": "뉴시스", "type": "rss", "url": google_rss("site:newsis.com 경제 OR 증시 OR 기업 OR 반도체")},
    {"name": "헤럴드경제", "type": "rss", "url": google_rss("site:heraldcorp.com 경제 OR 증시 OR 기업 OR 반도체")},
    {"name": "비즈워치", "type": "rss", "url": google_rss("site:bizwatch.co.kr 증시 OR 투자 OR 기업 OR 반도체")},
    {"name": "블로터", "type": "rss", "url": google_rss("site:bloter.net AI OR 반도체 OR 증시 OR 기업")},
    {"name": "더벨", "type": "rss", "url": google_rss("site:thebell.co.kr 투자 OR 증시 OR 반도체 OR 기업")},
    {"name": "국민일보", "type": "rss", "url": google_rss("site:kmib.co.kr 경제 OR 증시 OR 기업")},
]


# =========================================================
# 분류 사전
# =========================================================

POSITIVE = [
    "수주", "계약", "공급", "양산", "증설", "투자", "흑자", "호실적",
    "최초", "최고", "최대", "역대", "갱신", "상향", "돌파", "승인",
    "성장", "강세", "급등", "확대", "협력", "기대", "호재", "개선",
    "수혜", "신고가", "사상 최고", "반등", "회복", "증가", "확보",
    "선정", "채택", "성과", "호황", "순항", "출시", "개발", "상승",
    "랠리", "목표가 상향", "실적 개선", "턴어라운드", "흑자전환",
    "매출 증가", "영업익 증가", "수익성 개선", "완판", "대박",
    "재평가", "본격화", "국산화", "상장 추진", "대규모", "신사업",
]

NEGATIVE = [
    "적자", "감산", "규제", "소송", "리콜", "중단", "악화", "급락",
    "하락", "우려", "부진", "손실", "취소", "철회", "약세", "압박",
    "감소", "실패", "파업", "제재", "폭락", "경고", "쇼크", "둔화",
    "불확실", "위기", "타격", "하향", "퇴출", "논란", "과징금",
    "상장폐지", "거래정지", "압수수색",
]

COMPANY_RULES = {
    "삼성전자": ["삼성전자", "Samsung Electronics"],
    "SK하이닉스": ["SK하이닉스", "하이닉스", "SK Hynix"],
    "엔비디아": ["엔비디아", "NVIDIA", "루빈", "Rubin", "GPU"],
    "TSMC": ["TSMC"],
    "한미반도체": ["한미반도체", "TC본더", "본더"],
    "삼성전기": ["삼성전기", "FC-BGA", "패키지기판"],
    "현대차": ["현대차", "현대자동차", "Hyundai Motor"],
    "기아": ["기아"],
    "카카오": ["카카오"],
    "네이버": ["네이버", "NAVER"],
    "LG에너지솔루션": ["LG에너지솔루션", "LG엔솔"],
    "이수페타시스": ["이수페타시스"],
    "대덕전자": ["대덕전자"],
    "티엘비": ["티엘비"],
    "한화오션": ["한화오션"],
    "두산에너빌리티": ["두산에너빌리티"],
}

THEME_RULES = {
    "HBM": ["HBM", "HBM3E", "HBM4"],
    "AI": ["AI", "인공지능", "GPU", "엔비디아", "루빈", "데이터센터"],
    "반도체": ["반도체", "파운드리", "메모리", "D램", "DRAM", "낸드"],
    "PCB": ["PCB", "FC-BGA", "기판", "패키지기판"],
    "자동차": ["현대차", "기아", "전기차", "자동차"],
    "2차전지": ["배터리", "2차전지", "전고체"],
    "조선": ["조선", "LNG", "선박"],
    "원전": ["원전", "원자력"],
    "국장": ["코스피", "코스닥", "증시", "공시", "ETF", "상장", "시총"],
}

BAD_TITLE_WORDS = [
    "포토", "화보", "사진", "영상", "기자간담회", "작가간담회",
    "기자 모집", "수습기자", "채용", "공모", "공지", "알림",
    "로그인", "구독", "전체보기", "이전", "다음", "메뉴", "검색",
    "바로가기", "댓글", "공유", "기사목록", "많이 본 뉴스", "인기검색어",
    "서비스 약관", "개인정보", "저작권", "facebook", "instagram",
    "youtube", "트위터", "유튜브", "인스타그램", "페이스북",
    "오늘의 증시일정", "24시간 뉴스센터", "광고", "newsletter",
    "credit cards", "retire", "retirement", "wedding expenses",
    "hotel credit", "municipal bond", "KOREA NOW", "K-Culture NOW",
    "계약사", "제휴문의", "자주 묻는 질문", "보도자료", "국내배포",
    "해외배포", "Games", "공감 많은 뉴스", "오래 머문 뉴스",
    "이 시각 헤드라인", "The BeLT", "국제옵저버", "청소년보호정책",
    "수용자권익위원회", "연합뉴스 트위터", "연합뉴스 유튜브",
    "연합뉴스 인스타그램", "연합뉴스 페이스북",
]


# =========================================================
# 유틸
# =========================================================

def clean_text(x):
    return re.sub(r"\s+", " ", str(x or "")).strip()


def now_dt():
    return datetime.now(KST).replace(tzinfo=None)


def absolute_url(link, base):
    link = str(link or "")
    if link.startswith("http"):
        return link
    if link.startswith("//"):
        return "https:" + link
    if link.startswith("/"):
        return base + link
    return base + "/" + link


def parse_rss_dt(x):
    if not x:
        return None
    try:
        dt = parsedate_to_datetime(x)
        if dt.tzinfo:
            dt = dt.astimezone(KST)
        return dt.replace(tzinfo=None)
    except Exception:
        return None


def parse_text_dt(text):
    text = clean_text(text)

    patterns = [
        r"(\d{4})[-.](\d{2})[-.](\d{2})[.\s]+(오전|오후)?\s*(\d{1,2}):(\d{2})",
        r"(\d{4})[.](\d{2})[.](\d{2})[.]\s*(오전|오후)?\s*(\d{1,2}):(\d{2})",
    ]

    for p in patterns:
        m = re.search(p, text)
        if m:
            y, mo, d, ampm, h, mi = m.groups()
            h = int(h)
            if ampm == "오후" and h < 12:
                h += 12
            if ampm == "오전" and h == 12:
                h = 0
            return datetime(int(y), int(mo), int(d), h, int(mi))

    m = re.search(r"(\d{2})[-.](\d{2})\s+(\d{1,2}):(\d{2})", text)
    if m:
        mo, d, h, mi = map(int, m.groups())
        return datetime(now_dt().year, mo, d, h, mi)

    m = re.search(r"(\d+)\s*분\s*전", text)
    if m:
        return now_dt() - timedelta(minutes=int(m.group(1)))

    m = re.search(r"(\d+)\s*시간\s*전", text)
    if m:
        return now_dt() - timedelta(hours=int(m.group(1)))

    return None


def display_dt(dt):
    return "" if dt is None else dt.strftime("%m-%d %H:%M")


def clean_title_tail(title):
    title = clean_text(title)
    title = re.sub(r"\s+[가-힣A-Za-z0-9·.\-]+(\s+\d+\s*분\s*전|\s+\d+\s*시간\s*전)$", "", title)
    title = re.sub(r"\s+\d{4}[-.]\d{2}[-.]\d{2}.*\d{1,2}:\d{2}$", "", title)
    return clean_text(title)


def valid_title(title):
    title = clean_text(title)

    if not title or len(title) < 8 or len(title) > 220:
        return False

    if any(w.lower() in title.lower() for w in BAD_TITLE_WORDS):
        return False

    if re.match(r"^\d+\s*위[, ]", title):
        return False

    if len(re.sub(r"[가-힣A-Za-z0-9]", "", title)) > len(title) * 0.6:
        return False

    return True


def detect_sentiment(title):
    pos = sum(w in title for w in POSITIVE)
    neg = sum(w in title for w in NEGATIVE)

    if pos > neg:
        return "🔵 긍정"
    if neg > pos:
        return "🔴 부정"
    return "⚪ 중립"


def detect_company(title):
    found = []

    for c, words in COMPANY_RULES.items():
        if any(w.lower() in title.lower() for w in words):
            found.append(c)

    if "HBM" in title:
        found += ["삼성전자", "SK하이닉스", "한미반도체"]
    if "PCB" in title:
        found += ["이수페타시스", "대덕전자", "티엘비"]

    return ", ".join(dict.fromkeys(found)) if found else "미분류"


def detect_theme(title):
    found = []

    for t, words in THEME_RULES.items():
        if any(w.lower() in title.lower() for w in words):
            found.append(t)

    return ", ".join(dict.fromkeys(found)) if found else "기타"


def make_row(title, link, media, dt):
    title = clean_title_tail(title)

    if not valid_title(title):
        return None

    collected_at = now_dt()
    final_dt = dt if dt else collected_at

    return {
        "title": title,
        "display_title": title[:170] + "..." if len(title) > 170 else title,
        "sentiment": detect_sentiment(title),
        "company": detect_company(title),
        "theme": detect_theme(title),
        "media": media,
        "display_dt": display_dt(final_dt),
        "sort_dt": final_dt,
        "link": link,
        "inserted_at": collected_at,
    }


# =========================================================
# 수집 함수
# =========================================================

def fetch_rss(source):
    rows = []
    feed = feedparser.parse(source["url"])

    for item in feed.entries[:160]:
        raw = clean_text(item.get("title", ""))
        link = item.get("link", "")
        published = item.get("published") or item.get("updated") or ""

        if not valid_title(raw):
            continue

        title = raw
        media = source["name"]

        if source["url"].startswith("https://news.google.com") and " - " in raw:
            title, origin = raw.rsplit(" - ", 1)
            title = clean_text(title)
            media = clean_text(origin) or media

        row = make_row(title, link, media, parse_rss_dt(published))
        if row:
            rows.append(row)

    return rows


def fetch_daum_finance(source):
    rows, seen = [], set()

    rss_list = [
        google_rss("site:finance.daum.net 경제 OR 증시 OR 주식 OR 기업"),
        google_rss("site:v.daum.net 경제 OR 증시 OR 주식 OR 반도체 OR 기업"),
    ]

    for rss_url in rss_list:
        feed = feedparser.parse(rss_url)

        for item in feed.entries[:100]:
            raw = clean_text(item.get("title", ""))
            link = item.get("link", "")
            published = item.get("published") or item.get("updated") or ""

            if not valid_title(raw):
                continue

            title = raw
            media = "다음금융"

            if " - " in raw:
                title, origin = raw.rsplit(" - ", 1)
                title = clean_text(title)
                media = clean_text(origin) or "다음금융"

            key = title.lower().replace(" ", "")
            if key in seen:
                continue
            seen.add(key)

            row = make_row(title, link, media, parse_rss_dt(published))
            if row:
                rows.append(row)

    return rows


def fetch_naver_finance(source):
    rows, seen = [], set()

    try:
        for page in range(1, NAVER_FINANCE_PAGES + 1):
            url = (
                "https://finance.naver.com/news/news_list.naver"
                f"?mode=LSS2D&section_id=101&section_id2=258&page={page}"
                f"&_ts={int(datetime.now().timestamp())}"
            )

            res = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            res.encoding = "euc-kr"
            soup = BeautifulSoup(res.text, "lxml")

            links = soup.select(
                "dt.articleSubject a, "
                "dd.articleSubject a, "
                "a[href*='news_read.naver'], "
                "a[href*='article_id=']"
            )

            for a in links:
                title = clean_text(a.get_text(" ") or a.get("title", ""))
                href = a.get("href", "")

                if not valid_title(title):
                    continue

                link = absolute_url(href, source["base"])

                parent = (
                    a.find_parent("dl")
                    or a.find_parent("li")
                    or a.find_parent("dd")
                    or a.find_parent("dt")
                    or a.find_parent()
                )

                block_text = clean_text(parent.get_text(" ") if parent else "")

                next_dd = parent.find_next_sibling("dd") if parent else None
                if next_dd:
                    block_text += " " + clean_text(next_dd.get_text(" "))

                dt = parse_text_dt(block_text)

                key = title.lower().replace(" ", "")
                if key in seen:
                    continue

                seen.add(key)

                row = make_row(title, link, "네이버금융", dt)
                if row:
                    rows.append(row)

    except Exception:
        pass

    return rows


def fetch_naver_news(source):
    rows, seen = [], set()

    try:
        for page in range(1, NAVER_NEWS_PAGES + 1):
            url = (
                "https://news.naver.com/main/list.naver"
                f"?mode=LSD&mid=shm&sid1=101&page={page}"
                f"&_ts={int(datetime.now().timestamp())}"
            )

            res = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            res.encoding = "euc-kr"
            soup = BeautifulSoup(res.text, "lxml")

            items = soup.select("ul.type06_headline li, ul.type06 li")

            for item in items:
                a = item.select_one("dt:not(.photo) a") or item.select_one("a[href*='n.news.naver.com'], a[href*='read.naver']")
                if not a:
                    continue

                title = clean_text(a.get_text(" ") or a.get("title", ""))
                href = a.get("href", "")

                if not valid_title(title):
                    continue

                link = absolute_url(href, source["base"])
                block_text = clean_text(item.get_text(" "))
                dt = parse_text_dt(block_text)

                key = title.lower().replace(" ", "")
                if key in seen:
                    continue

                seen.add(key)

                row = make_row(title, link, "네이버뉴스", dt)
                if row:
                    rows.append(row)

    except Exception:
        pass

    return rows


def fetch_generic(source):
    rows, seen = [], set()

    try:
        res = requests.get(source["url"], headers=HEADERS, timeout=TIMEOUT)
        res.encoding = source.get("encoding") or res.apparent_encoding
        soup = BeautifulSoup(res.text, "lxml")

        allow = source.get("allow", [])

        for a in soup.find_all("a", href=True):
            title = clean_text(a.get_text(" "))
            href = a.get("href", "")
            link = absolute_url(href, source["base"])

            if allow and not any(x in link for x in allow):
                continue

            if not valid_title(title):
                continue

            key = title.lower().replace(" ", "")
            if key in seen:
                continue
            seen.add(key)

            block = a.find_parent("li") or a.find_parent("article") or a.find_parent()
            block_text = clean_text(block.get_text(" ") if block else "")
            dt = parse_text_dt(block_text)

            row = make_row(title, link, source["name"], dt)
            if row:
                rows.append(row)

    except Exception:
        pass

    return rows


def fetch_one(source):
    if source["type"] == "naver_finance":
        return fetch_naver_finance(source)
    if source["type"] == "naver_news":
        return fetch_naver_news(source)
    if source["type"] == "daum_finance":
        return fetch_daum_finance(source)
    if source["type"] == "rss":
        return fetch_rss(source)
    return fetch_generic(source)


def fetch_all():
    rows = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(fetch_one, s) for s in SOURCES]

        for future in as_completed(futures):
            try:
                rows.extend(future.result())
            except Exception:
                pass

    return rows


# =========================================================
# DB
# =========================================================

def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS news (
        title TEXT,
        display_title TEXT,
        sentiment TEXT,
        company TEXT,
        theme TEXT,
        media TEXT,
        display_dt TEXT,
        sort_dt TEXT,
        link TEXT UNIQUE,
        inserted_at TEXT
    )
    """)
    con.commit()
    con.close()


def save_rows(rows):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    for r in rows:
        cur.execute("""
        INSERT INTO news VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(link) DO UPDATE SET
            title=excluded.title,
            display_title=excluded.display_title,
            sentiment=excluded.sentiment,
            company=excluded.company,
            theme=excluded.theme,
            media=excluded.media,
            display_dt=excluded.display_dt,
            sort_dt=excluded.sort_dt,
            inserted_at=excluded.inserted_at
        """, (
            r["title"],
            r["display_title"],
            r["sentiment"],
            r["company"],
            r["theme"],
            r["media"],
            r["display_dt"],
            r["sort_dt"].isoformat() if r["sort_dt"] else "",
            r["link"],
            r["inserted_at"].isoformat(),
        ))

    con.commit()
    con.close()


def purge_old():
    cutoff = now_dt() - timedelta(hours=KEEP_HOURS)

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("DELETE FROM news WHERE inserted_at < ?", (cutoff.isoformat(),))
    con.commit()
    con.close()


def load_db():
    con = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM news", con)
    con.close()

    if df.empty:
        return df

    df["sort_dt_real"] = pd.to_datetime(df["sort_dt"], errors="coerce")
    df["inserted_real"] = pd.to_datetime(df["inserted_at"], errors="coerce")
    df["sort_key"] = df["sort_dt_real"].fillna(df["inserted_real"])

    df = df.sort_values(
        by="sort_key",
        ascending=False,
        kind="mergesort"
    ).reset_index(drop=True)

    return df


@st.cache_data(ttl=10)
def refresh():
    init_db()
    save_rows(fetch_all())
    purge_old()
    return load_db()


# =========================================================
# 화면
# =========================================================

st.title("📰 뉴스 터미널")
st.caption(f"10초 자동갱신 | 최근 {KEEP_HOURS}시간 누적 저장 | 시간순 정렬 | 제목 클릭 시 원문 이동")

if st.button("DB 완전 초기화 / 강제 새로고침"):
    st.cache_data.clear()

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    st.rerun()

df = refresh()

if df.empty:
    st.warning("뉴스가 없습니다.")
    st.stop()

c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 2])

with c1:
    sentiment_filter = st.selectbox("감성", ["전체", "🔵 긍정", "⚪ 중립", "🔴 부정"])

with c2:
    company_filter = st.selectbox("회사명", ["전체"] + sorted(df["company"].dropna().unique().tolist()))

with c3:
    theme_filter = st.selectbox("테마", ["전체"] + sorted(df["theme"].dropna().unique().tolist()))

with c4:
    media_filter = st.selectbox("매체", ["전체"] + sorted(df["media"].dropna().unique().tolist()))

with c5:
    search = st.text_input("검색")

filtered = df.copy()

if sentiment_filter != "전체":
    filtered = filtered[filtered["sentiment"] == sentiment_filter]

if company_filter != "전체":
    filtered = filtered[filtered["company"] == company_filter]

if theme_filter != "전체":
    filtered = filtered[filtered["theme"] == theme_filter]

if media_filter != "전체":
    filtered = filtered[filtered["media"] == media_filter]

if search:
    filtered = filtered[
        filtered["title"].str.contains(search, case=False, na=False)
        | filtered["company"].str.contains(search, case=False, na=False)
        | filtered["theme"].str.contains(search, case=False, na=False)
        | filtered["media"].str.contains(search, case=False, na=False)
    ]

st.subheader(f"전체 뉴스 {len(filtered)}개")

with st.expander("매체별 수집 개수 확인"):
    check = (
        df.groupby("media")
        .agg(전체=("title", "count"))
        .reset_index()
        .sort_values("전체", ascending=False)
    )
    st.dataframe(check, use_container_width=True, hide_index=True)

rows = ""

for _, r in filtered.head(1500).iterrows():
    rows += f"""
    <tr>
      <td class="title" title="{html.escape(str(r['title']))}">
        <a href="{html.escape(str(r['link']))}" target="_blank">{html.escape(str(r['display_title']))}</a>
      </td>
      <td class="sentiment">{html.escape(str(r['sentiment']))}</td>
      <td class="company">{html.escape(str(r['company']))}</td>
      <td class="theme">{html.escape(str(r['theme']))}</td>
      <td class="media">{html.escape(str(r['media']))}</td>
      <td class="date">{html.escape(str(r['display_dt']))}</td>
    </tr>
    """

components.html(f"""
<style>
.news-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 12.5px;
    table-layout: fixed;
}}
.news-table th {{
    background: #f1f3f5;
    padding: 7px 6px;
    border-bottom: 1px solid #ddd;
    text-align: left;
    font-weight: 700;
}}
.news-table td {{
    padding: 5px 6px;
    border-bottom: 1px solid #eee;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}
.news-table tr:hover {{
    background: #f8f9fa;
}}
.title {{
    width: 70%;
    font-weight: 600;
}}
.title a {{
    color: #005bac;
    text-decoration: none;
}}
.title a:hover {{
    text-decoration: underline;
}}
.sentiment {{
    width: 62px;
    font-weight: 700;
}}
.company {{
    width: 90px;
}}
.theme {{
    width: 68px;
}}
.media {{
    width: 90px;
}}
.date {{
    width: 105px;
}}
</style>

<table class="news-table">
<thead>
<tr>
<th class="title">제목</th>
<th class="sentiment">감성</th>
<th class="company">회사명</th>
<th class="theme">테마</th>
<th class="media">매체</th>
<th class="date">일자</th>
</tr>
</thead>
<tbody>{rows}</tbody>
</table>
""", height=850, scrolling=True)
