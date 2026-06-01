import streamlit as st
import feedparser
import pandas as pd
from urllib.parse import quote
from datetime import datetime
from email.utils import parsedate_to_datetime

st.set_page_config(page_title="주식 뉴스 터미널", layout="wide")

st.title("📰 주식 뉴스 터미널")
st.caption("일자 / 매체 / 제목 / 요약 / 중요도")

KEYWORDS = [
    "삼성전자",
    "SK하이닉스",
    "HBM",
    "반도체",
    "PCB",
    "엔비디아",
    "테슬라 옵티머스",
    "삼성전기",
    "한미반도체",
    "LG에너지솔루션"
]

IMPORTANT_WORDS = [
    "수주", "계약", "공급", "HBM", "엔비디아", "양산", "증설",
    "AI", "실적", "투자", "최대", "돌파", "급등", "강세",
    "반도체", "GPU", "메모리", "흑자", "상향", "목표가"
]

def format_date(date_text):
    try:
        dt = parsedate_to_datetime(date_text)
        return dt.strftime("%Y-%m-%d %H:%M")
    except:
        return date_text

def get_media(title):
    if " - " in title:
        return title.split(" - ")[-1].strip()
    return "구글뉴스"

def clean_title(title):
    if " - " in title:
        return " - ".join(title.split(" - ")[:-1]).strip()
    return title

def make_summary(title):
    text = clean_title(title)
    if len(text) > 45:
        return text[:45] + "..."
    return text

def get_importance(title):
    score = 1
    for word in IMPORTANT_WORDS:
        if word.lower() in title.lower():
            score += 1
    score = min(score, 5)
    return "⭐" * score

@st.cache_data(ttl=300)
def load_news():
    rows = []
    seen = set()

    for keyword in KEYWORDS:
        url = f"https://news.google.com/rss/search?q={quote(keyword)}&hl=ko&gl=KR&ceid=KR:ko"
        feed = feedparser.parse(url)

        for entry in feed.entries[:15]:
            title = entry.get("title", "")
            link = entry.get("link", "")
            published = entry.get("published", "")

            if not title or title in seen:
                continue

            seen.add(title)

            rows.append({
                "일자": format_date(published),
                "매체": get_media(title),
                "제목": clean_title(title),
                "요약": make_summary(title),
                "중요도": get_importance(title),
                "키워드": keyword,
                "링크": link
            })

    df = pd.DataFrame(rows)

    if not df.empty:
        df = df.sort_values("일자", ascending=False)

    return df

df = load_news()

if df.empty:
    st.error("뉴스를 불러오지 못했습니다.")
    st.stop()

col1, col2, col3 = st.columns([1, 1, 2])

with col1:
    keyword_filter = st.selectbox("키워드", ["전체"] + KEYWORDS)

with col2:
    media_filter = st.selectbox("매체", ["전체"] + sorted(df["매체"].unique().tolist()))

with col3:
    search = st.text_input("제목 검색")

filtered = df.copy()

if keyword_filter != "전체":
    filtered = filtered[filtered["키워드"] == keyword_filter]

if media_filter != "전체":
    filtered = filtered[filtered["매체"] == media_filter]

if search:
    filtered = filtered[filtered["제목"].str.contains(search, case=False, na=False)]

st.subheader(f"수집 뉴스: {len(filtered)}개")

st.dataframe(
    filtered[["일자", "매체", "제목", "요약", "중요도"]],
    use_container_width=True,
    height=600
)

st.divider()

st.subheader("카드형 보기")

for _, row in filtered.iterrows():
    with st.container(border=True):
        st.markdown(f"### [{row['제목']}]({row['링크']})")
        st.write(f"**일자:** {row['일자']}  |  **매체:** {row['매체']}  |  **중요도:** {row['중요도']}")
        st.write(f"**요약:** {row['요약']}")
        st.caption(f"검색키워드: {row['키워드']}")
