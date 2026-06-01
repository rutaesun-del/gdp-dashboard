import os
import re
import pandas as pd
import streamlit as st
import feedparser
from urllib.parse import quote
from email.utils import parsedate_to_datetime
from datetime import datetime

st.set_page_config(page_title="주식 뉴스 터미널", layout="wide")

st.title("📰 주식 뉴스 터미널")
st.caption("키움 뉴스 + 구글뉴스 + 한경 + 매경 통합")

KEYWORDS = [
    "삼성전자", "SK하이닉스", "HBM", "반도체", "PCB",
    "엔비디아", "테슬라 옵티머스", "삼성전기", "한미반도체",
    "LG에너지솔루션"
]

IMPORTANT_WORDS = [
    "속보", "단독", "수주", "계약", "공급", "양산", "증설",
    "투자", "실적", "흑자", "최대", "돌파", "급등", "강세",
    "HBM", "엔비디아", "AI", "GPU", "반도체", "메모리",
    "목표가", "상향", "승인", "인수", "합병"
]

NEGATIVE_WORDS = [
    "급락", "하락", "적자", "부진", "감소", "소송", "규제",
    "리콜", "철회", "중단", "감산", "우려", "악화"
]

FIXED_FEEDS = [
    ("한경 전체", "https://www.hankyung.com/feed/all-news"),
    ("한경 경제", "https://www.hankyung.com/feed/economy"),
    ("한경 증권", "https://www.hankyung.com/feed/finance"),
    ("매경 헤드라인", "https://www.mk.co.kr/rss/30000001/"),
    ("매경 경제", "https://www.mk.co.kr/rss/30100041/"),
]

def format_date(value):
    if not value:
        return ""
    try:
        return parsedate_to_datetime(value).strftime("%Y-%m-%d %H:%M")
    except:
        return str(value)[:16]

def split_google_title(title):
    if " - " in title:
        parts = title.rsplit(" - ", 1)
        return parts[0].strip(), parts[1].strip()
    return title.strip(), "구글뉴스"

def importance(title):
    score = 1
    for w in IMPORTANT_WORDS:
        if w.lower() in title.lower():
            score += 1
    for w in NEGATIVE_WORDS:
        if w.lower() in title.lower():
            score += 1
    return "⭐" * min(score, 5)

def summary(title):
    text = re.sub(r"\s+", " ", title).strip()
    return text[:70] + "..." if len(text) > 70 else text

@st.cache_data(ttl=300)
def load_web_news():
    rows = []
    seen = set()

    # 구글뉴스: 키워드별 검색
    for keyword in KEYWORDS:
        url = f"https://news.google.com/rss/search?q={quote(keyword)}&hl=ko&gl=KR&ceid=KR:ko"
        feed = feedparser.parse(url)

        for entry in feed.entries[:15]:
            raw_title = entry.get("title", "")
            link = entry.get("link", "")
            published = entry.get("published", "")

            title, media = split_google_title(raw_title)
            key = title + link

            if not title or key in seen:
                continue

            seen.add(key)

            rows.append({
                "일자": format_date(published),
                "매체": media,
                "제목": title,
                "요약": summary(title),
                "중요도": importance(title),
                "키워드": keyword,
                "출처구분": "구글뉴스",
                "링크": link
            })

    # 한경/매경 RSS
    for media_name, url in FIXED_FEEDS:
        feed = feedparser.parse(url)

        for entry in feed.entries[:30]:
            title = entry.get("title", "")
            link = entry.get("link", "")
            published = entry.get("published", "")

            key = title + link

            if not title or key in seen:
                continue

            seen.add(key)

            matched_keyword = "전체"
            for k in KEYWORDS:
                if k.lower() in title.lower():
                    matched_keyword = k
                    break

            rows.append({
                "일자": format_date(published),
                "매체": media_name,
                "제목": title,
                "요약": summary(title),
                "중요도": importance(title),
                "키워드": matched_keyword,
                "출처구분": "RSS",
                "링크": link
            })

    return pd.DataFrame(rows)

def load_kiwoom_news():
    path = "kiwoom_news.csv"

    if not os.path.exists(path):
        return pd.DataFrame(columns=["일자", "매체", "제목", "요약", "중요도", "키워드", "출처구분", "링크"])

    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
    except:
        df = pd.read_csv(path, encoding="cp949")

    required = ["일자", "매체", "제목", "요약", "중요도", "키워드", "출처구분", "링크"]

    for col in required:
        if col not in df.columns:
            df[col] = ""

    df["출처구분"] = "키움"
    df["매체"] = df["매체"].replace("", "키움뉴스")

    return df[required]

web_df = load_web_news()
kiwoom_df = load_kiwoom_news()

df = pd.concat([kiwoom_df, web_df], ignore_index=True)

if df.empty:
    st.error("뉴스 데이터가 없습니다.")
    st.stop()

df = df.drop_duplicates(subset=["제목"], keep="first")
df = df.sort_values("일자", ascending=False)

col1, col2, col3, col4 = st.columns([1, 1, 1, 2])

with col1:
    source_filter = st.selectbox("출처구분", ["전체"] + sorted(df["출처구분"].dropna().unique().tolist()))

with col2:
    keyword_filter = st.selectbox("키워드", ["전체"] + sorted(df["키워드"].dropna().unique().tolist()))

with col3:
    media_filter = st.selectbox("매체", ["전체"] + sorted(df["매체"].dropna().unique().tolist()))

with col4:
    search = st.text_input("제목 검색")

filtered = df.copy()

if source_filter != "전체":
    filtered = filtered[filtered["출처구분"] == source_filter]

if keyword_filter != "전체":
    filtered = filtered[filtered["키워드"] == keyword_filter]

if media_filter != "전체":
    filtered = filtered[filtered["매체"] == media_filter]

if search:
    filtered = filtered[filtered["제목"].str.contains(search, case=False, na=False)]

st.subheader(f"뉴스 {len(filtered)}개")

st.dataframe(
    filtered[["일자", "매체", "제목", "요약", "중요도", "키워드", "출처구분"]],
    use_container_width=True,
    height=600
)

st.divider()
st.subheader("카드형 보기")

for _, row in filtered.head(100).iterrows():
    with st.container(border=True):
        if row["링크"]:
            st.markdown(f"### [{row['제목']}]({row['링크']})")
        else:
            st.markdown(f"### {row['제목']}")

        st.write(
            f"**일자:** {row['일자']}  |  "
            f"**매체:** {row['매체']}  |  "
            f"**중요도:** {row['중요도']}  |  "
            f"**구분:** {row['출처구분']}"
        )
        st.write(f"**요약:** {row['요약']}")
        st.caption(f"키워드: {row['키워드']}")
