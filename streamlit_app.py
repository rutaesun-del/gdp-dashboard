import streamlit as st
import feedparser
import pandas as pd

st.set_page_config(
    page_title="주식 뉴스 터미널",
    layout="wide"
)

st.title("📰 주식 뉴스 터미널")

keywords = [
    "삼성전자",
    "SK하이닉스",
    "HBM",
    "반도체",
    "엔비디아"
]

rows = []

for keyword in keywords:

    url = (
        "https://news.google.com/rss/search?q="
        + keyword
        + "&hl=ko&gl=KR&ceid=KR:ko"
    )

    feed = feedparser.parse(url)

    for entry in feed.entries[:10]:

        rows.append({
            "키워드": keyword,
            "제목": entry.title,
            "링크": entry.link
        })

df = pd.DataFrame(rows)

st.write(f"뉴스 {len(df)}건")

for _, row in df.iterrows():

    st.markdown(
        f"### [{row['제목']}]({row['링크']})"
    )

    st.caption(
        f"키워드 : {row['키워드']}"
    )

st.divider()

st.dataframe(
    df,
    use_container_width=True
)
