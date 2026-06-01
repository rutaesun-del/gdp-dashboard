import streamlit as st
import pandas as pd
import feedparser
from streamlit_autorefresh import st_autorefresh
from email.utils import parsedate_to_datetime
from urllib.parse import quote

# -------------------------
# 기본설정
# -------------------------

st.set_page_config(
    page_title="뉴스 터미널",
    layout="wide"
)

st_autorefresh(
    interval=10000,
    key="news_refresh"
)

# -------------------------
# 키워드
# -------------------------

KEYWORDS = [

    "삼성전자",
    "SK하이닉스",
    "HBM",
    "HBM4",
    "엔비디아",
    "TSMC",
    "한미반도체",
    "PCB",
    "이수페타시스",
    "대덕전자",
    "티엘비",
    "AI 반도체",
    "테슬라",
    "옵티머스"

]

# -------------------------
# 감성
# -------------------------

POSITIVE = [
    "수주","계약","공급","양산","증설",
    "투자","흑자","호실적",
    "상향","돌파","승인"
]

NEGATIVE = [
    "적자","감산","규제","소송",
    "리콜","중단","악화",
    "급락","하락","우려"
]

# -------------------------
# 회사 추론
# -------------------------

COMPANY_RULES = {

    "삼성전자": ["삼성전자"],

    "SK하이닉스": [
        "SK하이닉스",
        "하이닉스"
    ],

    "엔비디아": [
        "엔비디아",
        "NVIDIA",
        "GPU"
    ],

    "TSMC": [
        "TSMC"
    ],

    "한미반도체": [
        "한미반도체",
        "TC본더"
    ],

    "테슬라": [
        "테슬라",
        "옵티머스"
    ],

    "이수페타시스": [
        "이수페타시스"
    ],

    "대덕전자": [
        "대덕전자"
    ],

    "티엘비": [
        "티엘비"
    ]
}

# -------------------------
# 테마
# -------------------------

THEME_RULES = {

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

    "반도체": [
        "반도체",
        "파운드리",
        "DRAM"
    ]
}

# -------------------------
# 함수
# -------------------------

def get_sentiment(title):

    pos = sum(
        word in title
        for word in POSITIVE
    )

    neg = sum(
        word in title
        for word in NEGATIVE
    )

    if pos > neg:
        return "🔵 긍정"

    if neg > pos:
        return "🔴 부정"

    return "⚪ 중립"


def get_company(title):

    found = []

    for company, words in COMPANY_RULES.items():

        for word in words:

            if word.lower() in title.lower():

                found.append(company)
                break

    if found:
        return ", ".join(found)

    return "미분류"


def get_theme(title):

    found = []

    for theme, words in THEME_RULES.items():

        for word in words:

            if word.lower() in title.lower():

                found.append(theme)
                break

    if found:
        return ", ".join(found)

    return "기타"


def format_date(value):

    try:

        return parsedate_to_datetime(
            value
        ).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    except:

        return value


# -------------------------
# 뉴스수집
# -------------------------

rows = []
seen = set()

for keyword in KEYWORDS:

    rss_url = (
        "https://news.google.com/rss/search?q="
        + quote(keyword)
        + "&hl=ko&gl=KR&ceid=KR:ko"
    )

    feed = feedparser.parse(rss_url)

    for item in feed.entries[:30]:

        title = item.get(
            "title",
            ""
        )

        link = item.get(
            "link",
            ""
        )

        published = item.get(
            "published",
            ""
        )

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
            "일자": format_date(
                published
            ),
            "매체": "Google News",
            "링크": link

        })

# -------------------------
# 데이터프레임
# -------------------------

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
    "10초 자동 갱신"
)

st.subheader("🔥 속보")

for _, row in df.head(10).iterrows():

    st.markdown(
        f"""
### [{row['제목']}]({row['링크']})

{row['감성']} | {row['회사명']} | {row['테마']}
"""
    )

st.divider()

st.subheader("전체 뉴스")

display_df = df[
    [
        "제목",
        "감성",
        "회사명",
        "테마",
        "일자"
    ]
]

st.dataframe(
    display_df,
    use_container_width=True,
    height=700
)
