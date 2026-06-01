import streamlit as st
import feedparser
import pandas as pd
from urllib.parse import quote

st.set_page_config(page_title="주식 뉴스 터미널", layout="wide")

st.title("📰 주식 뉴스 터미널")
st.caption("구글뉴스 RSS 기반 테스트 버전")

keywords = ["삼성전자", "SK하이닉스", "HBM", "반도체", "엔비디아"]

rows = []
errors = []

for keyword in keywords:
    try:
        encoded_keyword = quote(keyword)
        url = f"https://news.google.com/rss/search?q={encoded_keyword}&hl=ko&gl=KR&ceid=KR:ko"

        feed = feedparser.parse(url)

        if feed.bozo:
            errors.append(f"{keyword} RSS 파싱 경고: {feed.bozo_exception}")

        for entry in feed.entries[:10]:
            title = entry.get("title", "")
            link = entry.get("link", "")
            published = entry.get("published", "")

            if title:
                rows.append({
                    "키워드": keyword,
                    "시간": published,
                    "제목": title,
                    "링크": link
                })

    except Exception as e:
        errors.append(f"{keyword} 에러: {e}")

df = pd.DataFrame(rows)

st.subheader(f"수집 뉴스: {len(df)}개")

if errors:
    with st.expander("에러 확인"):
        for e in errors:
            st.write(e)

if df.empty:
    st.error("뉴스를 못 불러왔습니다. requirements.txt 저장 여부와 배포 로그를 확인하세요.")
else:
    for _, row in df.iterrows():
        st.markdown(f"### [{row['제목']}]({row['링크']})")
        st.caption(f"{row['키워드']} | {row['시간']}")

    st.divider()
    st.dataframe(df, use_container_width=True)
