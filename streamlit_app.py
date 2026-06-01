import streamlit as st
import feedparser
import pandas as pd
from urllib.parse import quote
from email.utils import parsedate_to_datetime

st.set_page_config(page_title="주식 뉴스 터미널", layout="wide")

# -------------------
# 회사명 사전
# -------------------

COMPANY_MAP = {
    "삼성전자": ["삼성전자"],
    "SK하이닉스": ["SK하이닉스", "하이닉스"],
    "삼성전기": ["삼성전기"],
    "한미반도체": ["한미반도체"],
    "엔비디아": ["엔비디아", "NVIDIA"],
    "테슬라": ["테슬라", "Tesla", "옵티머스"],
    "LG에너지솔루션": ["LG에너지솔루션"],
    "이수페타시스": ["이수페타시스"],
    "대덕전자": ["대덕전자"],
    "티엘비": ["티엘비"],
}

# -------------------
# 테마
# -------------------

THEME_MAP = {
    "HBM": ["HBM", "HBM3E", "HBM4", "D램", "DRAM"],
    "AI": ["AI", "인공지능", "GPU", "엔비디아"],
    "PCB": ["PCB", "FC-BGA", "기판"],
    "로봇": ["옵티머스", "휴머노이드", "로봇"],
    "2차전지": ["배터리", "2차전지", "전고체"],
}

# -------------------
# 감성
# -------------------

POSITIVE = [
    "수주","계약","공급","양산","증설",
    "투자","흑자","호실적","최대",
    "돌파","승인","협력","인수",
    "상향","성장"
]

NEGATIVE = [
    "적자","감산","규제","소송",
    "리콜","중단","급락","하락",
    "악화","우려","실패","취소"
]

# -------------------
# 함수
# -------------------

def get_sentiment(title):

    pos = sum(word in title for word in POSITIVE)
    neg = sum(word in title for word in NEGATIVE)

    if pos > neg:
        return "긍정 🔴"

    if neg > pos:
        return "부정 🔵"

    return "중립 ⚪"


def get_company(title):

    result = []

    for company, words in COMPANY_MAP.items():

        for word in words:

            if word.lower() in title.lower():

                result.append(company)
                break

    if result:
        return ", ".join(result)

    return "미분류"


def get_theme(title):

    result = []

    for theme, words in THEME_MAP.items():

        for word in words:

            if word.lower() in title.lower():

                result.append(theme)
                break

    if result:
        return ", ".join(result)

    return "기타"


def format_date(text):

    try:
        return parsedate_to_datetime(text).strftime("%Y-%m-%d %H:%M")
    except:
        return text


# -------------------
# 뉴스 수집
# -------------------

feeds = []

# 구글뉴스

for keyword in [
    "삼성전자",
    "SK하이닉스",
    "HBM",
    "반도체",
    "엔비디아"
]:

    feeds.append(
        (
            "구글뉴스",
            f"https://news.google.com/rss/search?q={quote(keyword)}&hl=ko&gl=KR&ceid=KR:ko"
        )
    )

# 네이버

feeds.append(
    (
        "네이버",
        "https://news.google.com/rss/search?q=site:naver.com+반도체&hl=ko&gl=KR&ceid=KR:ko"
    )
)

# 한경

feeds.append(
    (
        "한국경제",
        "https://www.hankyung.com/feed/all-news"
    )
)

# 매경

feeds.append(
    (
        "매일경제",
        "https://www.mk.co.kr/rss/30000001/"
    )
)

rows = []

for media, url in feeds:

    feed = feedparser.parse(url)

    for item in feed.entries[:30]:

        title = item.get("title", "")
        link = item.get("link", "")
        pub = item.get("published", "")

        rows.append(
            {
                "제목": title,
                "중요도": get_sentiment(title),
                "회사명": get_company(title),
                "테마": get_theme(title),
                "일자": format_date(pub),
                "매체": media,
                "링크": link
            }
        )

df = pd.DataFrame(rows)

if not df.empty:
    df = df.sort_values(
        by="일자",
        ascending=False
    )

# -------------------
# 화면
# -------------------

st.title("📰 주식 뉴스 터미널")

st.dataframe(
    df[
        [
            "제목",
            "중요도",
            "회사명",
            "테마",
            "일자",
            "매체"
        ]
    ],
    use_container_width=True
)

st.divider()

for _, row in df.head(100).iterrows():

    with st.container():

        st.markdown(
            f"### [{row['제목']}]({row['링크']})"
        )

        st.write(
            f"중요도: {row['중요도']}"
        )

        st.write(
            f"회사명: {row['회사명']}"
        )

        st.write(
            f"테마: {row['테마']}"
        )

        st.write(
            f"일자: {row['일자']}"
        )

        st.write(
            f"매체: {row['매체']}"
        )

        st.divider()
