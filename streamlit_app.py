import re
import html
import requests
import feedparser
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup
from datetime import datetime
from email.utils import parsedate_to_datetime
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="뉴스 터미널", layout="wide")
st_autorefresh(interval=10000, key="news_refresh")

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

POSITIVE = [
    "수주", "계약", "공급", "양산", "증설", "투자", "흑자", "호실적",
    "상향", "돌파", "승인", "성장", "강세", "급등", "최대", "확대",
    "협력", "개발", "기대", "호재", "개선"
]

NEGATIVE = [
    "적자", "감산", "규제", "소송", "리콜", "중단", "악화", "급락",
    "하락", "우려", "부진", "손실", "취소", "철회", "약세", "압박",
    "감소"
]

COMPANY_RULES = {
    "삼성전자": ["삼성전자", "삼성", "갤럭시", "파운드리"],
    "SK하이닉스": ["SK하이닉스", "하이닉스"],
    "엔비디아": ["엔비디아", "NVIDIA", "GPU", "루빈", "Rubin"],
    "TSMC": ["TSMC", "대만 TSMC"],
    "한미반도체": ["한미반도체", "TC본더", "본더"],
    "삼성전기": ["삼성전기", "FC-BGA", "패키지기판"],
    "테슬라": ["테슬라", "옵티머스", "Tesla"],
    "LG에너지솔루션": ["LG에너지솔루션", "LG엔솔"],
    "이수페타시스": ["이수페타시스"],
    "대덕전자": ["대덕전자"],
    "티엘비": ["티엘비"],
    "마이크론": ["마이크론", "Micron"],
    "AMD": ["AMD"],
    "브로드컴": ["브로드컴", "Broadcom"],
}

THEME_RULES = {
    "HBM": ["HBM", "HBM3E", "HBM4"],
    "AI": ["AI", "인공지능", "GPU", "엔비디아", "루빈", "데이터센터"],
    "반도체": ["반도체", "파운드리", "메모리", "D램", "DRAM", "낸드"],
    "PCB": ["PCB", "FC-BGA", "기판", "패키지기판"],
    "로봇": ["옵티머스", "휴머노이드", "로봇"],
    "2차전지": ["배터리", "2차전지", "전고체"],
}

SOURCES = [
    {
        "name": "구글뉴스",
        "type": "rss",
        "url": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko"
    },
    {
        "name": "한국경제",
        "type": "rss",
        "url": "https://www.hankyung.com/feed/all-news"
    },
    {
        "name": "한국경제-증권",
        "type": "rss",
        "url": "https://www.hankyung.com/feed/finance"
    },
    {
        "name": "매일경제",
        "type": "rss",
        "url": "https://www.mk.co.kr/rss/30000001/"
    },
    {
        "name": "Yahoo Finance",
        "type": "rss",
        "url": "https://finance.yahoo.com/news/rssindex"
    },
    {
        "name": "네이버금융",
        "type": "crawl",
        "url": "https://finance.naver.com/news/mainnews.naver",
        "base": "https://finance.naver.com"
    },
    {
        "name": "다음경제",
        "type": "crawl",
        "url": "https://news.daum.net/breakingnews/economic",
        "base": "https://news.daum.net"
    },
    {
        "name": "아시아경제",
        "type": "crawl",
        "url": "https://www.asiae.co.kr/news/list.htm?sec=eco99",
        "base": "https://www.asiae.co.kr"
    },
    {
        "name": "한국일보",
        "type": "crawl",
        "url": "https://www.hankookilbo.com/News/Economy",
        "base": "https://www.hankookilbo.com"
    },
]

def clean_text(text):
    return re.sub(r"\s+", " ", text or "").strip()

def absolute_url(link, base):
    if not link:
        return ""
    if link.startswith("http"):
        return link
    if link.startswith("//"):
        return "https:" + link
    if link.startswith("/"):
        return base + link
    return base + "/" + link

def format_date(value):
    if not value:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        return parsedate_to_datetime(value).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def detect_sentiment(title):
    pos = sum(word in title for word in POSITIVE)
    neg = sum(word in title for word in NEGATIVE)

    if pos > neg:
        return "🔵 긍정"
    if neg > pos:
        return "🔴 부정"
    return "⚪ 중립"

def detect_company(title):
    found = []
    for company, words in COMPANY_RULES.items():
        if any(word.lower() in title.lower() for word in words):
            found.append(company)
    return ", ".join(dict.fromkeys(found)) if found else "미분류"

def detect_theme(title):
    found = []
    for theme, words in THEME_RULES.items():
        if any(word.lower() in title.lower() for word in words):
            found.append(theme)
    return ", ".join(dict.fromkeys(found)) if found else "기타"

def fetch_rss(source):
    rows = []
    feed = feedparser.parse(source["url"])

    for item in feed.entries[:80]:
        raw_title = clean_text(item.get("title", ""))
        link = item.get("link", "")
        published = item.get("published", "")

        if not raw_title:
            continue

        title = raw_title
        media = source["name"]

        if " - " in raw_title and source["name"] == "구글뉴스":
            parts = raw_title.rsplit(" - ", 1)
            title = clean_text(parts[0])
            media = clean_text(parts[1])

        rows.append({
            "제목": title,
            "감성": detect_sentiment(title),
            "회사명": detect_company(title),
            "테마": detect_theme(title),
            "매체": media,
            "일자": format_date(published),
            "링크": link
        })

    return rows

def fetch_crawl(source):
    rows = []

    try:
        res = requests.get(source["url"], headers=HEADERS, timeout=8)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "lxml")

        candidates = []

        for a in soup.find_all("a", href=True):
            title = clean_text(a.get_text(" "))
            href = a.get("href", "")

            if len(title) < 12:
                continue

            if any(x in title for x in ["로그인", "구독", "전체보기", "이전", "다음", "메뉴"]):
                continue

            link = absolute_url(href, source["base"])

            if not link.startswith("http"):
                continue

            candidates.append((title, link))

        seen_local = set()

        for title, link in candidates[:120]:
            key = title.lower()
            if key in seen_local:
                continue
            seen_local.add(key)

            rows.append({
                "제목": title,
                "감성": detect_sentiment(title),
                "회사명": detect_company(title),
                "테마": detect_theme(title),
                "매체": source["name"],
                "일자": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "링크": link
            })

    except Exception:
        pass

    return rows

@st.cache_data(ttl=10)
def load_news():
    rows = []

    for source in SOURCES:
        if source["type"] == "rss":
            rows.extend(fetch_rss(source))
        else:
            rows.extend(fetch_crawl(source))

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    df["중복키"] = df["제목"].str.lower().str.replace(" ", "", regex=False)
    df = df.drop_duplicates(subset=["중복키"], keep="first")
    df = df.drop(columns=["중복키"])
    df = df.sort_values("일자", ascending=False)

    return df

st.title("📰 뉴스 터미널")
st.caption("10초 자동갱신 | 전체 뉴스 수집 후 제목 기준 자동분류")

df = load_news()

if df.empty:
    st.warning("뉴스가 없습니다.")
    st.stop()

col1, col2, col3, col4 = st.columns([1, 1, 1, 2])

with col1:
    sentiment_filter = st.selectbox("감성", ["전체"] + sorted(df["감성"].unique().tolist()))

with col2:
    company_filter = st.selectbox("회사명", ["전체"] + sorted(df["회사명"].unique().tolist()))

with col3:
    theme_filter = st.selectbox("테마", ["전체"] + sorted(df["테마"].unique().tolist()))

with col4:
    search = st.text_input("검색")

filtered = df.copy()

if sentiment_filter != "전체":
    filtered = filtered[filtered["감성"] == sentiment_filter]

if company_filter != "전체":
    filtered = filtered[filtered["회사명"] == company_filter]

if theme_filter != "전체":
    filtered = filtered[filtered["테마"] == theme_filter]

if search:
    filtered = filtered[
        filtered["제목"].str.contains(search, case=False, na=False)
        | filtered["회사명"].str.contains(search, case=False, na=False)
        | filtered["테마"].str.contains(search, case=False, na=False)
        | filtered["매체"].str.contains(search, case=False, na=False)
    ]

st.subheader(f"전체 뉴스 {len(filtered)}개")

for _, row in filtered.head(300).iterrows():
    with st.container(border=True):
        st.markdown(f"### [{row['제목']}]({row['링크']})")
        st.write(
            f"{row['감성']} | "
            f"회사명: {row['회사명']} | "
            f"테마: {row['테마']} | "
            f"매체: {row['매체']} | "
            f"일자: {row['일자']}"
        )
