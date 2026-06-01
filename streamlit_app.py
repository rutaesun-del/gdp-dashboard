import re, html, sqlite3, requests, feedparser, os
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="뉴스 터미널", layout="wide")
st_autorefresh(interval=20000, key="refresh")

KST = timezone(timedelta(hours=9))
DB_PATH = "news_terminal_final_v2.db"
KEEP_HOURS = 24
NAVER_FINANCE_PAGES = 20
NAVER_NEWS_PAGES = 10

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
}

def google_rss(q):
    return f"https://news.google.com/rss/search?q={quote(q)}&hl=ko&gl=KR&ceid=KR:ko"

SOURCES = [
    {"name":"네이버금융","type":"naver_finance","url":"https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258","base":"https://finance.naver.com","encoding":"euc-kr"},
    {"name":"네이버뉴스","type":"naver_news","url":"https://news.naver.com/main/list.naver?mode=LSD&mid=shm&sid1=101","base":"https://news.naver.com","encoding":"euc-kr"},

    {"name":"한국경제","type":"rss","url":"https://www.hankyung.com/feed/all-news"},
    {"name":"한국경제-증권","type":"rss","url":"https://www.hankyung.com/feed/finance"},
    {"name":"매일경제","type":"rss","url":"https://www.mk.co.kr/rss/30000001/"},
    {"name":"구글뉴스-경제","type":"rss","url":"https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko"},

    {"name":"다음뉴스","type":"generic","url":"https://finance.daum.net/news#economy","base":"https://finance.daum.net","encoding":"utf-8"},
    {"name":"아시아경제","type":"generic","url":"https://www.asiae.co.kr/news/list.htm?sec=eco99","base":"https://www.asiae.co.kr","encoding":"utf-8"},
    {"name":"한국일보","type":"generic","url":"https://www.hankookilbo.com/News/Economy","base":"https://www.hankookilbo.com","encoding":"utf-8"},
    {"name":"전자신문","type":"generic","url":"https://www.etnews.com/news/section.html?id1=20","base":"https://www.etnews.com","encoding":"utf-8"},
    {"name":"ZDNet","type":"generic","url":"https://zdnet.co.kr/news/?lstcode=0000","base":"https://zdnet.co.kr","encoding":"utf-8"},
    {"name":"디지털데일리","type":"generic","url":"https://www.ddaily.co.kr/page/list/0/0","base":"https://www.ddaily.co.kr","encoding":"utf-8"},
    {"name":"조선비즈","type":"generic","url":"https://biz.chosun.com/stock/","base":"https://biz.chosun.com","encoding":"utf-8"},
    {"name":"서울경제","type":"generic","url":"https://www.sedaily.com/NewsList/GA","base":"https://www.sedaily.com","encoding":"utf-8"},
    {"name":"파이낸셜뉴스","type":"generic","url":"https://www.fnnews.com/section/002000000","base":"https://www.fnnews.com","encoding":"utf-8"},
    {"name":"이데일리","type":"generic","url":"https://www.edaily.co.kr/News/stock","base":"https://www.edaily.co.kr","encoding":"utf-8"},
    {"name":"머니투데이","type":"generic","url":"https://news.mt.co.kr/newsList.html?pDepth1=stock","base":"https://news.mt.co.kr","encoding":"utf-8"},
    {"name":"연합뉴스","type":"generic","url":"https://www.yna.co.kr/economy/all","base":"https://www.yna.co.kr","encoding":"utf-8"},
    {"name":"뉴스1","type":"generic","url":"https://www.news1.kr/economy","base":"https://www.news1.kr","encoding":"utf-8"},

    {"name":"더벨","type":"rss","url":google_rss("site:thebell.co.kr 기업 OR 투자 OR 증시 OR 반도체")},
    {"name":"블로터","type":"rss","url":google_rss("site:bloter.net 기업 OR AI OR 반도체 OR 증시")},
    {"name":"비즈워치","type":"rss","url":google_rss("site:bizwatch.co.kr 기업 OR 증시 OR 투자")},
    {"name":"뉴시스","type":"rss","url":google_rss("site:newsis.com 경제 OR 증시 OR 기업")},
    {"name":"헤럴드경제","type":"rss","url":google_rss("site:heraldcorp.com 경제 OR 증시 OR 기업")},
    {"name":"국민일보","type":"rss","url":google_rss("site:kmib.co.kr 경제 OR 증시 OR 기업")},
]

POSITIVE = [
    "수주","계약","공급","양산","증설","투자","흑자","호실적","최초","최고","최대","역대","갱신",
    "상향","돌파","승인","성장","강세","급등","확대","협력","기대","호재","개선","수혜","신고가",
    "사상 최고","반등","회복","증가","확보","선정","채택","성과","호황","순항","출시","개발",
    "상승","랠리","목표가 상향","실적 개선","턴어라운드","흑자전환","매출 증가","영업익 증가",
    "수익성 개선","완판","대박","재평가","본격화","국산화","상장 추진","대규모","신사업"
]

NEGATIVE = [
    "적자","감산","규제","소송","리콜","중단","악화","급락","하락","우려","부진","손실","취소",
    "철회","약세","압박","감소","실패","파업","제재","폭락","경고","쇼크","둔화","불확실",
    "위기","타격","하향","퇴출","논란","과징금","상장폐지","거래정지","압수수색"
]

COMPANY_RULES = {
    "삼성전자":["삼성전자","Samsung Electronics"],
    "SK하이닉스":["SK하이닉스","하이닉스","SK Hynix"],
    "엔비디아":["엔비디아","NVIDIA","루빈","Rubin","GPU"],
    "TSMC":["TSMC"],
    "한미반도체":["한미반도체","TC본더","본더"],
    "삼성전기":["삼성전기","FC-BGA","패키지기판"],
    "현대차":["현대차","현대자동차","Hyundai Motor"],
    "기아":["기아"],
    "카카오":["카카오"],
    "네이버":["네이버","NAVER"],
    "LG에너지솔루션":["LG에너지솔루션","LG엔솔"],
    "이수페타시스":["이수페타시스"],
    "대덕전자":["대덕전자"],
    "티엘비":["티엘비"],
    "마이크론":["마이크론","Micron"],
    "AMD":["AMD"],
    "한화오션":["한화오션"],
    "두산에너빌리티":["두산에너빌리티"],
}

THEME_RULES = {
    "HBM":["HBM","HBM3E","HBM4"],
    "AI":["AI","인공지능","GPU","엔비디아","루빈","데이터센터"],
    "반도체":["반도체","파운드리","메모리","D램","DRAM","낸드"],
    "PCB":["PCB","FC-BGA","기판","패키지기판"],
    "자동차":["현대차","기아","전기차","자동차"],
    "2차전지":["배터리","2차전지","전고체"],
    "조선":["조선","LNG","선박"],
    "원전":["원전","원자력"],
    "국장":["코스피","코스닥","증시","공시","ETF","상장","시총"],
}

BAD_TITLE_WORDS = [
    "포토","화보","사진","영상","기자간담회","작가간담회","기자 모집","수습기자",
    "마감","채용","공모","공지","알림","로그인","구독","전체보기","이전","다음",
    "메뉴","검색","바로가기","댓글","공유","기사목록","많이 본 뉴스","인기검색어",
    "서비스 약관","개인정보","저작권","facebook","instagram","youtube",
    "오늘의 증시일정","24시간 뉴스센터","광고","newsletter",
    "credit cards","retire","retirement","wedding expenses","hotel credit","municipal bond"
]

def clean_text(x):
    return re.sub(r"\s+", " ", str(x or "")).strip()

def now_dt():
    return datetime.now(KST).replace(tzinfo=None)

def absolute_url(link, base):
    link = str(link or "")
    if link.startswith("http"): return link
    if link.startswith("//"): return "https:" + link
    if link.startswith("/"): return base + link
    return base + "/" + link

def parse_rss_dt(x):
    if not x: return None
    try:
        dt = parsedate_to_datetime(x)
        if dt.tzinfo:
            dt = dt.astimezone(KST)
        return dt.replace(tzinfo=None)
    except:
        return None

def parse_text_dt(text):
    text = clean_text(text)

    m = re.search(r"(\d{4})[-.](\d{2})[-.](\d{2})[.\s]+(오전|오후)?\s*(\d{1,2}):(\d{2})", text)
    if m:
        y, mo, d, ampm, h, mi = m.groups()
        h = int(h)
        if ampm == "오후" and h < 12: h += 12
        if ampm == "오전" and h == 12: h = 0
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
    return True

def detect_sentiment(title):
    pos = sum(w in title for w in POSITIVE)
    neg = sum(w in title for w in NEGATIVE)
    if pos > neg: return "🔵 긍정"
    if neg > pos: return "🔴 부정"
    return "⚪ 중립"

def detect_company(title):
    found = []
    for c, words in COMPANY_RULES.items():
        if any(w.lower() in title.lower() for w in words):
            found.append(c)
    if "HBM" in title: found += ["삼성전자","SK하이닉스","한미반도체"]
    if "PCB" in title: found += ["이수페타시스","대덕전자","티엘비"]
    return ", ".join(dict.fromkeys(found)) if found else "미분류"

def detect_theme(title):
    found = []
    for t, words in THEME_RULES.items():
        if any(w.lower() in title.lower() for w in words):
            found.append(t)
    return ", ".join(dict.fromkeys(found)) if found else "기타"

def make_row(title, link, media, dt):
    title = clean_title_tail(title)

    if dt is None:
        return None

    if not valid_title(title):
        return None

    return {
        "title": title,
        "display_title": title[:170] + "..." if len(title) > 170 else title,
        "sentiment": detect_sentiment(title),
        "company": detect_company(title),
        "theme": detect_theme(title),
        "media": media,
        "display_dt": display_dt(dt),
        "sort_dt": dt,
        "link": link,
        "inserted_at": now_dt(),
    }

def fetch_rss(source):
    rows = []
    feed = feedparser.parse(source["url"])

    for item in feed.entries[:180]:
        raw = clean_text(item.get("title", ""))
        link = item.get("link", "")
        published = item.get("published") or item.get("updated") or ""

        if not valid_title(raw): continue

        title = raw
        media = source["name"]

        if source["url"].startswith("https://news.google.com") and " - " in raw:
            title, origin = raw.rsplit(" - ", 1)
            title = clean_text(title)
            media = clean_text(origin) or media

        row = make_row(title, link, media, parse_rss_dt(published))
        if row: rows.append(row)

    return rows

def fetch_naver_finance(source):
    rows, seen = [], set()

    try:
        for page in range(1, NAVER_FINANCE_PAGES + 1):
            url = source["url"] + f"&page={page}&_ts=" + str(int(datetime.now().timestamp()))
            res = requests.get(url, headers=HEADERS, timeout=8)
            res.encoding = source["encoding"]
            soup = BeautifulSoup(res.text, "lxml")

            for item in soup.select("dl.newsList"):
                block_text = clean_text(item.get_text(" "))

                for a in item.select("dt.articleSubject a, dd.articleSubject a, a[href*='news_read.naver'], a[href*='article_id=']"):
                    title = clean_text(a.get_text(" "))
                    href = a.get("href", "")

                    if not valid_title(title): continue

                    key = title.lower().replace(" ", "")
                    if key in seen: continue
                    seen.add(key)

                    link = absolute_url(href, source["base"])
                    dt = parse_text_dt(block_text)

                    row = make_row(title, link, source["name"], dt)
                    if row: rows.append(row)

    except:
        pass

    return rows

def fetch_naver_news(source):
    rows, seen = [], set()

    try:
        for page in range(1, NAVER_NEWS_PAGES + 1):
            url = source["url"] + f"&page={page}&_ts=" + str(int(datetime.now().timestamp()))
            res = requests.get(url, headers=HEADERS, timeout=8)
            res.encoding = source["encoding"]
            soup = BeautifulSoup(res.text, "lxml")

            for a in soup.select("a[href*='n.news.naver.com'], a[href*='news.naver.com/main/read']"):
                title = clean_text(a.get_text(" "))
                href = a.get("href", "")

                if not valid_title(title): continue

                key = title.lower().replace(" ", "")
                if key in seen: continue
                seen.add(key)

                link = absolute_url(href, source["base"])
                block = a.find_parent("li") or a.find_parent()
                dt = parse_text_dt(clean_text(block.get_text(" ") if block else ""))

                row = make_row(title, link, source["name"], dt)
                if row: rows.append(row)

    except:
        pass

    return rows

def fetch_generic(source):
    rows, seen = [], set()

    try:
        res = requests.get(source["url"], headers=HEADERS, timeout=8)
        res.encoding = source.get("encoding") or res.apparent_encoding
        soup = BeautifulSoup(res.text, "lxml")

        for a in soup.find_all("a", href=True):
            title = clean_text(a.get_text(" "))
            href = a.get("href", "")

            if not valid_title(title): continue

            key = title.lower().replace(" ", "")
            if key in seen: continue
            seen.add(key)

            link = absolute_url(href, source["base"])
            block = a.find_parent("li") or a.find_parent("article") or a.find_parent()
            dt = parse_text_dt(clean_text(block.get_text(" ") if block else ""))

            row = make_row(title, link, source["name"], dt)
            if row: rows.append(row)

    except:
        pass

    return rows

def fetch_all():
    rows = []
    for s in SOURCES:
        if s["type"] == "naver_finance":
            rows.extend(fetch_naver_finance(s))
        elif s["type"] == "naver_news":
            rows.extend(fetch_naver_news(s))
        elif s["type"] == "rss":
            rows.extend(fetch_rss(s))
        else:
            rows.extend(fetch_generic(s))
    return rows

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
        INSERT OR IGNORE INTO news VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            r["title"], r["display_title"], r["sentiment"], r["company"], r["theme"],
            r["media"], r["display_dt"], r["sort_dt"].isoformat(),
            r["link"], r["inserted_at"].isoformat()
        ))
    con.commit()
    con.close()

def purge():
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
    df = df.dropna(subset=["sort_dt_real"])
    df = df.sort_values("sort_dt_real", ascending=False)

    return df

@st.cache_data(ttl=20)
def refresh():
    init_db()
    save_rows(fetch_all())
    purge()
    return load_db()

st.title("📰 뉴스 터미널")
st.caption(f"20초 자동갱신 | 최근 {KEEP_HOURS}시간 누적 저장 | 날짜 없는 기사 제외 | 일자 내림차순")

if st.button("DB 완전 초기화 / 강제 새로고침"):
    st.cache_data.clear()
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    st.rerun()

df = refresh()

if df.empty:
    st.warning("뉴스가 없습니다.")
    st.stop()

c1, c2, c3, c4, c5 = st.columns([1,1,1,1,2])

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
    check = df.groupby("media").agg(
        전체=("title","count")
    ).reset_index().sort_values("전체", ascending=False)
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
.news-table {{width:100%; border-collapse:collapse; font-size:12.5px; table-layout:fixed;}}
.news-table th {{background:#f1f3f5; padding:7px 6px; border-bottom:1px solid #ddd; text-align:left;}}
.news-table td {{padding:5px 6px; border-bottom:1px solid #eee; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}}
.news-table tr:hover {{background:#f8f9fa;}}
.title {{width:70%; font-weight:600;}}
.title a {{color:#005bac; text-decoration:none;}}
.title a:hover {{text-decoration:underline;}}
.sentiment {{width:62px; font-weight:700;}}
.company {{width:90px;}}
.theme {{width:68px;}}
.media {{width:90px;}}
.date {{width:105px;}}
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
