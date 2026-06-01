import streamlit as st
import pandas as pd
import feedparser
from streamlit_autorefresh import st_autorefresh
from email.utils import parsedate_to_datetime

# -------------------------
# 자동 새로고침 10초
# -------------------------

st_autorefresh(interval=10000, key="news_refresh")

st.set_page_config(
    page_title="뉴스 터미널",
    layout="wide"
)

# -------------------------
# 감성
# -------------------------

POSITIVE = [
    "수주","계약","공급","양산","증설",
    "투자","흑자","호실적","상향",
    "돌파","승인","성장"
]

NEGATIVE = [
    "적자","감산","규제","소송",
    "리콜","중단","악화",
    "급락","하락","우려"
]

# -------------------------
# 회사 추론
# -------------------------

KNOWLEDGE = {

    "루빈": [
        "엔비디아",
        "TSMC",
        "삼성전자",
        "SK하이닉스"
    ],

    "HBM": [
        "삼성전자",
        "SK하이닉스",
        "한미반도체"
    ],

    "HBM4": [
        "삼성전자",
        "SK하이닉스",
        "한미반도체"
    ],

    "PCB": [
        "이수페타시스",
        "대덕전자",
        "티엘비"
    ],

    "옵티머스": [
        "테슬라"
    ]
}

# -------------------------
# 테마
# -------------------------

THEMES = {

    "HBM": [
        "HBM",
        "HBM3E",
        "HBM4"
    ],

    "AI": [
        "AI",
        "GPU",
        "엔비디아",
        "루빈"
    ],

    "PCB": [
        "PCB",
        "FC-BGA",
        "기판"
    ],

    "로봇": [
        "옵티머스",
        "휴머노이드",
        "로봇"
    ],

    "2차전지": [
        "배터리",
        "전고체",
        "2차전지"
    ]
}

# -------------------------
# 함수
# -------------------------

def get_sentiment(title):

    pos = sum(word in title for word in POSITIVE)
    neg = sum(word in title for word in NEGATIVE)

    if pos > neg:
        return "🔵 긍정"

    if neg > pos:
        return "🔴 부정"

    return "⚪ 중립"


def get_company(title):

    result = []

    for keyword, companies in KNOWLEDGE.items():

        if keyword.lower() in title.lower():

            result.extend(companies)

    result = list(set(result))

    if result:
        return ", ".join(result)

    return "미분류"


def get_theme(title):

    result = []

    for theme, words in THEMES.items():

        for word in words:

            if word.lower() in title.lower():

                result.append(theme)
                break

    if result:
        return ", ".join(result)

    return "기타"


def format_date(value):

    try:
        return parsedate_to_datetime(
            value
        ).strftime("%Y-%m-%d %H:%M:%S")

    except:
        return value

# -------------------------
# 뉴스 소스
# -------------------------

RSS_LIST = [

    (
        "구글뉴스",
        "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko"
    ),

    (
        "한국경제",
        "https://www.hankyung.com/feed/all-news"
    ),

    (
        "매일경제",
        "https://www.mk.co.kr/rss/30000001/"
    ),

    (
        "네이버",
        "https://news.google.com/rss/search?q=site:naver.com&hl=ko&gl=KR&ceid=KR:ko"
    ),

    (
        "다음",
        "https://news.google.com/rss/search?q=site:v.daum.net&hl=ko&gl=KR&ceid=KR:ko"
    )

]

# -------------------------
# 수집
# -------------------------

rows = []
seen = set()

for media, url in RSS_LIST:

    feed = feedparser.parse(url)

    for item in feed.entries[:200]:

        title = item.get("title", "")
        link = item.get("link", "")
        published = item.get("published", "")

        if not title:
            continue

        key = title.lower()

        if key in seen:
            continue

        seen.add(key)

        rows.append({

            "제목": title,
            "감성": get_sentiment(title),
            "회사명": get_company(title),
            "테마": get_theme(title),
            "일자": format_date(published),
            "매체": media,
            "링크": link

        })

df = pd.DataFrame(rows)

if not df.empty:

    df = df.sort_values(
        by="일자",
        ascending=False
    )

# -------------------------
# 화면
# -------------------------

st.title("📰 뉴스 터미널")

st.caption(
    "10초 자동갱신 | 제목 클릭 시 원문 이동"
)

# 속보

st.subheader("🔥 속보")

for _, row in df.head(10).iterrows():

    st.markdown(
        f"**[{row['제목']}]({row['링크']})**"
    )

# 전체 뉴스

st.subheader("전체 뉴스")

for _, row in df.iterrows():

    st.markdown(
        f"""
### [{row['제목']}]({row['링크']})

{row['감성']} | {row['회사명']} | {row['테마']}

🕒 {row['일자']} | 📰 {row['매체']}

---
"""
    )
