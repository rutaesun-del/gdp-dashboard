import re
import html
import requests
import feedparser
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from streamlit_autorefresh import st_autorefresh


st.set_page_config(page_title="뉴스 터미널", layout="wide")
st_autorefresh(interval=10000, key="refresh")

KST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
}


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
        "name": "다음경제",
        "type": "generic",
        "url": "https://news.daum.net/economy",
        "base": "https://news.daum.net",
        "encoding": "utf-8",
        "allow": ["v.daum.net", "news.v.daum.net"],
    },
    {
        "name": "한국경제",
        "type": "rss",
        "url": "https://www.hankyung.com/feed/all-news",
    },
    {
        "name": "한국경제-증권",
        "type": "rss",
        "url": "https://www.hankyung.com/feed/finance",
    },
    {
        "name": "매일경제",
        "type": "rss",
        "url": "https://www.mk.co.kr/rss/30000001/",
    },
    {
        "name": "아시아경제",
        "type": "generic",
        "url": "https://www.asiae.co.kr/news/list.htm?sec=eco99",
        "base": "https://www.asiae.co.kr",
        "encoding": "utf-8",
        "allow": ["asiae.co.kr/article", "view.htm"],
    },
    {
        "name": "한국일보",
        "type": "generic",
        "url": "https://www.hankookilbo.com/News/Economy",
        "base": "https://www.hankookilbo.com",
        "encoding": "utf-8",
        "allow": ["hankookilbo.com/News/Read"],
    },
    {
        "name": "구글뉴스",
        "type": "rss",
        "url": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko",
    },
]


POSITIVE = [
    "수주", "계약", "공급", "양산", "증설", "투자", "흑자", "호실적",
    "최초", "최고", "최대", "역대", "갱신", "상향", "돌파", "승인",
    "성장", "강세", "급등", "확대", "협력", "기대", "호재", "개선",
    "수혜", "신고가", "사상 최고", "반등", "회복", "증가", "확보",
    "선정", "채택", "성과", "호황", "순항", "출시", "개발", "상승",
    "랠리", "점유율 확대", "목표가 상향", "실적 개선", "턴어라운드",
]

NEGATIVE = [
    "적자", "감산", "규제", "소송", "리콜", "중단", "악화", "급락",
    "하락", "우려", "부진", "손실", "취소", "철회", "약세", "압박",
    "감소", "실패", "파업", "제재", "폭락", "경고", "쇼크", "둔화",
    "불확실", "위기", "타격", "하향", "손상", "매각", "퇴출",
]

COMPANY_RULES = {
    "삼성전자": ["삼성전자", "삼성"],
    "SK하이닉스": ["SK하이닉스", "하이닉스"],
    "엔비디아": ["엔비디아", "NVIDIA", "루빈", "Rubin", "GPU"],
    "TSMC": ["TSMC"],
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
    "현대차": ["현대차", "현대자동차"],
    "기아": ["기아"],
    "카카오": ["카카오"],
    "네이버": ["네이버", "NAVER"],
}

KNOWLEDGE_RULES = {
    "HBM": ["삼성전자", "SK하이닉스", "한미반도체"],
    "HBM4": ["삼성전자", "SK하이닉스", "한미반도체"],
    "루빈": ["엔비디아", "TSMC", "삼성전자", "SK하이닉스"],
    "Rubin": ["엔비디아", "TSMC", "삼성전자", "SK하이닉스"],
    "PCB": ["이수페타시스", "대덕전자", "티엘비"],
    "FC-BGA": ["삼성전기", "대덕전자"],
    "옵티머스": ["테슬라"],
}

THEME_RULES = {
    "HBM": ["HBM", "HBM3E", "HBM4"],
    "AI": ["AI", "인공지능", "GPU", "엔비디아", "루빈", "데이터센터"],
    "반도체": ["반도체", "파운드리", "메모리", "D램", "DRAM", "낸드"],
    "PCB": ["PCB", "FC-BGA", "기판", "패키지기판"],
    "로봇": ["옵티머스", "휴머노이드", "로봇"],
    "2차전지": ["배터리", "2차전지", "전고체"],
    "자동차": ["현대차", "기아", "전기차", "자동차"],
}


def clean_text(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def clean_title_tail(title):
    title = clean_text(title)

    title = re.sub(
        r"\s+[가-힣A-Za-z0-9·.\-]+(\s+\d+\s*분\s*전|\s+\d+\s*시간\s*전)$",
        "",
        title,
    )

    title = re.sub(r"\s+\d{4}[-.]\d{2}[-.]\d{2}\s+\d{2}:\d{2}$", "", title)

    return clean_text(title)


def absolute_url(link, base):
    link = str(link or "")

    if not link:
        return ""

    if link.startswith("http"):
        return link

    if link.startswith("//"):
        return "https:" + link

    if link.startswith("/"):
        return base + link

    return base + "/" + link


def now_dt():
    return datetime.now(KST).replace(tzinfo=None)


def parse_rss_dt(value):
    if not value:
        return None

    try:
        dt = parsedate_to_datetime(value)

        if dt.tzinfo:
            dt = dt.astimezone(KST)

        return dt.replace(tzinfo=None)

    except Exception:
        return None


def parse_text_dt(text):
    text = clean_text(text)

    m = re.search(r"(\d{4})[-.](\d{2})[-.](\d{2})\s+(\d{2}):(\d{2})", text)
    if m:
        y, mo, d, h, mi = map(int, m.groups())
        return datetime(y, mo, d, h, mi)

    m = re.search(r"(\d{2})[-.](\d{2})\s+(\d{2}):(\d{2})", text)
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
    if dt is None:
        return ""

    return dt.strftime("%m-%d %H:%M")


def valid_title(title):
    title = clean_text(title)

    if not title:
        return False

    if len(title) < 10 or len(title) > 180:
        return False

    bad_words = [
        "로그인", "구독", "전체보기", "이전", "다음", "메뉴", "검색",
        "바로가기", "댓글", "공유", "기사목록", "많이 본 뉴스",
        "인기검색어", "뉴스 검색", "오늘의 증시일정", "서비스 약관",
        "개인정보처리방침", "저작권", "facebook", "facebook_gray",
        "instagram", "insta_gray", "youtube", "youtube_gray",
        "Visual-News", "©", "AZ Corp", "뉴스센터", "24시간 뉴스센터",
        "저작물 구매안내", "소셜 아이콘", "개인정보", "고객센터",
        "신규", "상승", "하락", "보합", "고가", "저가",
    ]

    if any(word.lower() in title.lower() for word in bad_words):
        return False

    if re.match(r"^\d+\s*위[, ]", title):
        return False

    if re.match(r"^\d+\.\d+", title):
        return False

    if len(re.sub(r"[가-힣A-Za-z0-9]", "", title)) > len(title) * 0.55:
        return False

    return True


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

    for key, companies in KNOWLEDGE_RULES.items():
        if key.lower() in title.lower():
            found.extend(companies)

    return ", ".join(dict.fromkeys(found)) if found else "미분류"


def detect_theme(title):
    found = []

    for theme, words in THEME_RULES.items():
        if any(word.lower() in title.lower() for word in words):
            found.append(theme)

    return ", ".join(dict.fromkeys(found)) if found else "기타"


def make_row(title, link, media, dt):
    title = clean_title_tail(title)

    return {
        "제목": title,
        "표시제목": title[:170] + "..." if len(title) > 170 else title,
        "감성": detect_sentiment(title),
        "회사명": detect_company(title),
        "테마": detect_theme(title),
        "매체": media,
        "일자": display_dt(dt),
        "정렬일자": dt,
        "링크": link,
    }


def fetch_rss(source):
    rows = []

    feed = feedparser.parse(source["url"])

    for item in feed.entries[:150]:
        raw_title = clean_text(item.get("title", ""))
        link = item.get("link", "")
        published = item.get("published") or item.get("updated") or ""

        if not valid_title(raw_title):
            continue

        title = raw_title
        media = source["name"]

        if source["name"] == "구글뉴스" and " - " in raw_title:
            title, media = raw_title.rsplit(" - ", 1)
            title = clean_text(title)
            media = clean_text(media)

        if not valid_title(title):
            continue

        rows.append(make_row(title, link, media, parse_rss_dt(published)))

    return rows


def fetch_naver_finance(source):
    rows = []

    try:
        url = source["url"] + "&_ts=" + str(int(datetime.now().timestamp()))
        res = requests.get(url, headers=HEADERS, timeout=8)
        res.encoding = source.get("encoding", "euc-kr")

        soup = BeautifulSoup(res.text, "lxml")
        candidates = []

        selectors = [
            "dl.newsList dt.articleSubject a",
            "dl.newsList dd.articleSubject a",
            "dt.articleSubject a",
            "dd.articleSubject a",
            "a[href*='news_read.naver']",
            "a[href*='article_id=']",
        ]

        for selector in selectors:
            for a in soup.select(selector):
                title = clean_text(a.get_text(" "))
                href = a.get("href", "")

                if not valid_title(title):
                    continue

                link = absolute_url(href, source["base"])

                block = (
                    a.find_parent("li")
                    or a.find_parent("dl")
                    or a.find_parent("dd")
                    or a.find_parent("dt")
                    or a.find_parent()
                )

                block_text = clean_text(block.get_text(" ") if block else "")

                next_sibling = block.find_next_sibling() if block else None
                if next_sibling:
                    block_text += " " + clean_text(next_sibling.get_text(" "))

                dt = parse_text_dt(block_text)

                candidates.append((title, link, dt))

        seen = set()

        for title, link, dt in candidates[:200]:
            key = title.lower().replace(" ", "")

            if key in seen:
                continue

            seen.add(key)
            rows.append(make_row(title, link, source["name"], dt))

    except Exception:
        pass

    return rows


def fetch_naver_news(source):
    rows = []

    try:
        url = source["url"] + "&_ts=" + str(int(datetime.now().timestamp()))
        res = requests.get(url, headers=HEADERS, timeout=8)
        res.encoding = source.get("encoding", "euc-kr")

        soup = BeautifulSoup(res.text, "lxml")
        candidates = []

        for a in soup.select("a[href*='n.news.naver.com'], a[href*='news.naver.com/main/read']"):
            title = clean_text(a.get_text(" "))
            href = a.get("href", "")

            if not valid_title(title):
                continue

            link = absolute_url(href, source["base"])

            block = a.find_parent("li") or a.find_parent()
            block_text = clean_text(block.get_text(" ") if block else "")

            dt = parse_text_dt(block_text)

            candidates.append((title, link, dt))

        seen = set()

        for title, link, dt in candidates[:200]:
            key = title.lower().replace(" ", "")

            if key in seen:
                continue

            seen.add(key)
            rows.append(make_row(title, link, source["name"], dt))

    except Exception:
        pass

    return rows


def fetch_generic(source):
    rows = []

    try:
        res = requests.get(source["url"], headers=HEADERS, timeout=8)

        enc = source.get("encoding")
        if enc:
            res.encoding = enc
        elif res.apparent_encoding:
            res.encoding = res.apparent_encoding

        soup = BeautifulSoup(res.text, "lxml")
        candidates = []
        allow = source.get("allow", [])

        for a in soup.find_all("a", href=True):
            title = clean_text(a.get_text(" "))
            href = a.get("href", "")

            if not valid_title(title):
                continue

            link = absolute_url(href, source["base"])

            if not link.startswith("http"):
                continue

            if allow and not any(pattern in link for pattern in allow):
                continue

            block = a.find_parent("li") or a.find_parent("article") or a.find_parent()
            block_text = clean_text(block.get_text(" ") if block else "")

            dt = parse_text_dt(block_text)

            candidates.append((title, link, dt))

        seen = set()

        for title, link, dt in candidates[:200]:
            key = title.lower().replace(" ", "")

            if key in seen:
                continue

            seen.add(key)
            rows.append(make_row(title, link, source["name"], dt))

    except Exception:
        pass

    return rows


@st.cache_data(ttl=10)
def load_news():
    rows = []

    for source in SOURCES:
        if source["type"] == "rss":
            rows.extend(fetch_rss(source))
        elif source["type"] == "naver_finance":
            rows.extend(fetch_naver_finance(source))
        elif source["type"] == "naver_news":
            rows.extend(fetch_naver_news(source))
        else:
            rows.extend(fetch_generic(source))

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    df["중복키"] = df["제목"].str.lower().str.replace(" ", "", regex=False)
    df = df.drop_duplicates(subset=["중복키"], keep="first")
    df = df.drop(columns=["중복키"])

    df["정렬일자_보정"] = df["정렬일자"].fillna(datetime(1900, 1, 1))
    df = df.sort_values("정렬일자_보정", ascending=False)
    df = df.drop(columns=["정렬일자_보정"])

    return df


st.title("📰 실시간 뉴스")
st.caption("10초 자동갱신 | 제목 클릭 시 원문 이동")

if st.button("캐시 초기화 / 강제 새로고침"):
    st.cache_data.clear()
    st.rerun()

df = load_news()

if df.empty:
    st.warning("뉴스가 없습니다.")
    st.stop()

col1, col2, col3, col4, col5 = st.columns([1, 1, 1, 1, 2])

with col1:
    sentiment_filter = st.selectbox("감성", ["전체"] + sorted(df["감성"].unique().tolist()))

with col2:
    company_filter = st.selectbox("회사명", ["전체"] + sorted(df["회사명"].unique().tolist()))

with col3:
    theme_filter = st.selectbox("테마", ["전체"] + sorted(df["테마"].unique().tolist()))

with col4:
    media_filter = st.selectbox("매체", ["전체"] + sorted(df["매체"].unique().tolist()))

with col5:
    search = st.text_input("검색")

filtered = df.copy()

if sentiment_filter != "전체":
    filtered = filtered[filtered["감성"] == sentiment_filter]

if company_filter != "전체":
    filtered = filtered[filtered["회사명"] == company_filter]

if theme_filter != "전체":
    filtered = filtered[filtered["테마"] == theme_filter]

if media_filter != "전체":
    filtered = filtered[filtered["매체"] == media_filter]

if search:
    filtered = filtered[
        filtered["제목"].str.contains(search, case=False, na=False)
        | filtered["회사명"].str.contains(search, case=False, na=False)
        | filtered["테마"].str.contains(search, case=False, na=False)
        | filtered["매체"].str.contains(search, case=False, na=False)
    ]

st.subheader(f"전체 뉴스 {len(filtered)}개")

with st.expander("매체별 최신 시간 / 수집 개수 확인"):
    check = (
        df.groupby("매체")
        .agg(
            최신=("정렬일자", "max"),
            개수=("제목", "count"),
        )
        .reset_index()
    )

    check["최신"] = check["최신"].apply(display_dt)
    st.dataframe(check, use_container_width=True, hide_index=True)

rows_html = ""

for _, row in filtered.head(1000).iterrows():
    title = html.escape(str(row["표시제목"]))
    full_title = html.escape(str(row["제목"]))
    link = html.escape(str(row["링크"]))
    sentiment = html.escape(str(row["감성"]))
    company = html.escape(str(row["회사명"]))
    theme = html.escape(str(row["테마"]))
    media = html.escape(str(row["매체"]))
    date = html.escape(str(row["일자"]))

    rows_html += f"""
    <tr>
        <td class="title" title="{full_title}">
            <a href="{link}" target="_blank">{title}</a>
        </td>
        <td class="sentiment">{sentiment}</td>
        <td class="company">{company}</td>
        <td class="theme">{theme}</td>
        <td class="media">{media}</td>
        <td class="date">{date}</td>
    </tr>
    """

table_html = f"""
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
    vertical-align: middle;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}
.news-table tr:hover {{
    background: #f8f9fa;
}}
.news-table .title {{
    width: 70%;
    font-weight: 600;
}}
.news-table .title a {{
    color: #005bac;
    text-decoration: none;
}}
.news-table .title a:hover {{
    text-decoration: underline;
}}
.news-table .sentiment {{
    width: 62px;
    font-weight: 700;
}}
.news-table .company {{
    width: 90px;
}}
.news-table .theme {{
    width: 68px;
}}
.news-table .media {{
    width: 90px;
}}
.news-table .date {{
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
    <tbody>
        {rows_html}
    </tbody>
</table>
"""

components.html(table_html, height=850, scrolling=True)
