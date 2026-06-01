import re, html, os, sqlite3, requests, feedparser
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="뉴스 터미널", layout="wide")
st_autorefresh(interval=15000, key="refresh")

KST = timezone(timedelta(hours=9))
DB_PATH = "NEWS_TERMINAL_CLEAN_RESET_V1.db"
KEEP_HOURS = 24
TIMEOUT = 6
ARTICLE_TIMEOUT = 4
MAX_WORKERS = 8
MAX_ARTICLES_PER_SOURCE = 60

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
}

POSITIVE = ["수주","계약","공급","양산","증설","투자","흑자","호실적","최초","최고","최대","역대","갱신","상향","돌파","승인","성장","강세","급등","확대","협력","기대","호재","개선","수혜","신고가","사상 최고","반등","회복","증가","확보","선정","채택","성과","호황","출시","개발","상승","랠리","목표가 상향","실적 개선","턴어라운드","흑자전환","매출 증가","영업익 증가","수익성 개선","재평가","본격화","국산화","대규모","신사업"]
NEGATIVE = ["적자","감산","규제","소송","리콜","중단","악화","급락","하락","우려","부진","손실","취소","철회","약세","압박","감소","실패","파업","제재","폭락","경고","쇼크","둔화","불확실","위기","타격","하향","퇴출","논란","과징금","거래정지","압수수색"]

STOCK_WORDS = ["주식","증시","코스피","코스닥","상장","공시","투자","수주","계약","공급","양산","증설","실적","매출","영업익","흑자","적자","목표가","증권","기관","외국인","시총","ETF","반도체","AI","HBM","GPU","데이터센터","2차전지","배터리","전기차","자동차","조선","원전","로봇","방산","바이오","제약","디스플레이","삼성전자","SK하이닉스","하이닉스","엔비디아","현대차","기아","카카오","네이버","LG","한화","두산","셀트리온","에코프로","포스코","TSMC","마이크론","OLED","D램","낸드"]

BAD_WORDS = ["포토","화보","사진","영상","갤러리","운세","별자리","책꽂이","미술","문학","작가","시인","채용","공모","공지","알림","로그인","구독","전체보기","메뉴","검색","댓글","공유","많이 본 뉴스","인기검색어","저작권","facebook","instagram","youtube","유튜브","인스타그램","페이스북","트위터","오늘의 증시일정","24시간 뉴스센터","광고","KOREA NOW","K-Culture","제휴문의","자주 묻는 질문","보도자료","Games","날씨","폭염","호우","장마","태풍","살해","경찰","검찰","재판","구속","맛집","여행","공연","연예","배우","가수","드라마","영화"]

COMPANY = {
    "삼성전자":["삼성전자"], "SK하이닉스":["SK하이닉스","하이닉스"], "엔비디아":["엔비디아","NVIDIA","루빈","GPU"],
    "TSMC":["TSMC"], "한미반도체":["한미반도체","TC본더"], "삼성전기":["삼성전기","FC-BGA"],
    "현대차":["현대차","현대자동차"], "기아":["기아"], "카카오":["카카오"], "네이버":["네이버","NAVER"],
    "LG에너지솔루션":["LG에너지솔루션","LG엔솔"], "이수페타시스":["이수페타시스"], "대덕전자":["대덕전자"],
    "티엘비":["티엘비"], "한화오션":["한화오션"], "두산에너빌리티":["두산에너빌리티"]
}

THEME = {
    "AI":["AI","인공지능","GPU","엔비디아","데이터센터"],
    "반도체":["반도체","HBM","파운드리","메모리","D램","DRAM","낸드"],
    "PCB":["PCB","FC-BGA","기판","패키지기판"],
    "자동차":["현대차","기아","전기차","자동차"],
    "2차전지":["배터리","2차전지","전고체"],
    "조선":["조선","LNG","선박"],
    "원전":["원전","원자력"],
    "증시":["코스피","코스닥","증시","ETF","상장","시총"]
}

def now():
    return datetime.now(KST).replace(tzinfo=None)

def txt(x):
    return re.sub(r"\s+", " ", str(x or "")).strip()

def abs_url(href, base):
    if href.startswith("http"): return href
    if href.startswith("//"): return "https:" + href
    if href.startswith("/"): return base + href
    return base + "/" + href

def gnews(q):
    return f"https://news.google.com/rss/search?q={quote(q)}&hl=ko&gl=KR&ceid=KR:ko"

def norm_title(t):
    t = txt(t)
    t = re.sub(r"\[[^\]]+\]|\([^)]*\)", "", t)
    t = re.sub(r"[^가-힣A-Za-z0-9]", "", t)
    return t.lower()

def valid_title(t):
    t = txt(t)
    if len(t) < 8 or len(t) > 180: return False
    if any(w.lower() in t.lower() for w in BAD_WORDS): return False
    if re.match(r"^\d+\s*위", t): return False
    return True

def stock_related(t):
    l = t.lower()
    return any(w.lower() in l for w in STOCK_WORDS)

def parse_date(s):
    s = txt(s)
    if not s: return None
    try:
        ss = s.replace("Z", "+00:00")
        if "T" in ss:
            d = datetime.fromisoformat(ss)
        else:
            d = parsedate_to_datetime(ss)
        if d.tzinfo:
            d = d.astimezone(KST)
        return d.replace(tzinfo=None)
    except:
        pass

    pats = [
        r"(\d{4})[-.](\d{1,2})[-.](\d{1,2})[.\s]+(오전|오후)?\s*(\d{1,2}):(\d{2})",
        r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일\s*(오전|오후)?\s*(\d{1,2}):(\d{2})",
    ]
    for p in pats:
        m = re.search(p, s)
        if m:
            y, mo, da, ap, h, mi = m.groups()
            h = int(h)
            if ap == "오후" and h < 12: h += 12
            if ap == "오전" and h == 12: h = 0
            return datetime(int(y), int(mo), int(da), h, int(mi))
    return None

def recent(d):
    if not d: return False
    return now() - timedelta(hours=KEEP_HOURS) <= d <= now() + timedelta(minutes=5)

def article_time(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=ARTICLE_TIMEOUT)
        r.encoding = r.apparent_encoding
        s = BeautifulSoup(r.text, "lxml")
        cand = []

        for attr in [
            {"property":"article:published_time"}, {"property":"og:regDate"}, {"name":"date"},
            {"name":"pubdate"}, {"name":"publish-date"}, {"itemprop":"datePublished"}
        ]:
            m = s.find("meta", attr)
            if m and m.get("content"): cand.append(m.get("content"))

        selectors = [
            ".media_end_head_info_datestamp_time","span._ARTICLE_DATE_TIME",".articleInfo .date",".article_info .date",
            ".num_date",".txt_date",".txt-date",".article-timestamp",".registration",".time_area",
            ".view_time",".news_dates",".dates",".article_date",".update-time",".txt-time",".date",".time","time"
        ]
        for sel in selectors:
            for tag in s.select(sel):
                if tag.get("datetime"): cand.append(tag.get("datetime"))
                cand.append(tag.get_text(" "))

        for c in cand:
            d = parse_date(c)
            if recent(d): return d
    except:
        return None
    return None

def sentiment(t):
    p = sum(w in t for w in POSITIVE)
    n = sum(w in t for w in NEGATIVE)
    if p > n: return "🔵 긍정"
    if n > p: return "🔴 부정"
    return "⚪ 중립"

def company(t):
    out = []
    for k, arr in COMPANY.items():
        if any(w.lower() in t.lower() for w in arr): out.append(k)
    return ", ".join(dict.fromkeys(out)) if out else "미분류"

def theme(t):
    out = []
    for k, arr in THEME.items():
        if any(w.lower() in t.lower() for w in arr): out.append(k)
    return ", ".join(dict.fromkeys(out)) if out else "기타"

def row(title, link, media, dt=None):
    title = txt(title)
    if " - " in title and media.startswith("구글"):
        title = txt(title.rsplit(" - ", 1)[0])
    if not valid_title(title): return None

    d = dt if recent(dt) else article_time(link)
    if not recent(d): return None

    return {
        "title": title,
        "display_title": title[:150] + "..." if len(title) > 150 else title,
        "sentiment": sentiment(title),
        "company": company(title),
        "theme": theme(title),
        "media": media,
        "display_dt": d.strftime("%m-%d %H:%M"),
        "sort_ts": d.timestamp(),
        "stock_related": 1 if stock_related(title) else 0,
        "dedupe_key": norm_title(title),
        "link": link,
        "inserted_at": now().isoformat()
    }

def rss_source(name, url, limit=80):
    rows = []
    f = feedparser.parse(url)
    for e in f.entries[:limit]:
        title = txt(e.get("title",""))
        link = e.get("link","")
        d = parse_date(e.get("published") or e.get("updated") or "")
        r = row(title, link, name, d)
        if r: rows.append(r)
    return rows

def naver_finance():
    rows, seen = [], set()
    for page in range(1, 8):
        try:
            url = f"https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258&page={page}"
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            r.encoding = "euc-kr"
            s = BeautifulSoup(r.text, "lxml")
            links = s.select("dt.articleSubject a, dd.articleSubject a, a[href*='news_read.naver']")
            for a in links:
                title = txt(a.get_text(" ") or a.get("title",""))
                link = abs_url(a.get("href",""), "https://finance.naver.com")
                k = norm_title(title)
                if not k or k in seen: continue
                seen.add(k)
                block = a.find_parent("dl") or a.find_parent("li") or a.find_parent()
                d = parse_date(txt(block.get_text(" ") if block else ""))
                rr = row(title, link, "네이버금융", d)
                if rr: rows.append(rr)
        except: pass
    return rows

def naver_news():
    rows, seen = [], set()
    for page in range(1, 4):
        try:
            url = f"https://news.naver.com/main/list.naver?mode=LSD&mid=shm&sid1=101&page={page}"
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            r.encoding = "euc-kr"
            s = BeautifulSoup(r.text, "lxml")
            for li in s.select("ul.type06_headline li, ul.type06 li"):
                a = li.select_one("dt:not(.photo) a") or li.select_one("a[href]")
                if not a: continue
                title = txt(a.get_text(" ") or a.get("title",""))
                link = abs_url(a.get("href",""), "https://news.naver.com")
                k = norm_title(title)
                if not k or k in seen: continue
                seen.add(k)
                d = parse_date(txt(li.get_text(" ")))
                rr = row(title, link, "네이버뉴스", d)
                if rr: rows.append(rr)
        except: pass
    return rows

def daum_finance():
    rows, seen = [], set()
    for url in ["https://news.daum.net/finance", "https://m.finance.daum.net/news"]:
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            r.encoding = "utf-8"
            s = BeautifulSoup(r.text, "lxml")
            for a in s.find_all("a", href=True)[:100]:
                title = txt(a.get_text(" "))
                href = a.get("href","")
                if "v.daum.net" not in href and "/v/" not in href: continue
                link = href if href.startswith("http") else abs_url(href, "https://news.daum.net")
                k = norm_title(title)
                if not k or k in seen: continue
                seen.add(k)
                block = a.find_parent("li") or a.find_parent("article") or a.find_parent()
                d = parse_date(txt(block.get_text(" ") if block else ""))
                rr = row(title, link, "다음금융", d)
                if rr: rows.append(rr)
        except: pass
    rows += rss_source("다음금융", gnews("site:v.daum.net 주식 OR 증시 OR 코스피 OR 코스닥 OR 반도체 OR 기업"), 60)
    return rows

def generic(name, url, base, allow):
    rows, seen = [], set()
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.encoding = r.apparent_encoding
        s = BeautifulSoup(r.text, "lxml")
        for a in s.find_all("a", href=True)[:160]:
            title = txt(a.get_text(" "))
            link = abs_url(a.get("href",""), base)
            if allow and not any(x in link for x in allow): continue
            k = norm_title(title)
            if not k or k in seen: continue
            seen.add(k)
            block = a.find_parent("li") or a.find_parent("article") or a.find_parent()
            d = parse_date(txt(block.get_text(" ") if block else ""))
            rr = row(title, link, name, d)
            if rr: rows.append(rr)
            if len(rows) >= MAX_ARTICLES_PER_SOURCE: break
    except: pass
    return rows

def collect():
    tasks = [
        naver_finance, naver_news, daum_finance,
        lambda: rss_source("한국경제", "https://www.hankyung.com/feed/all-news"),
        lambda: rss_source("한국경제-증권", "https://www.hankyung.com/feed/finance"),
        lambda: rss_source("매일경제", "https://www.mk.co.kr/rss/30000001/"),
        lambda: rss_source("구글뉴스-경제", "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko"),
        lambda: generic("서울경제","https://www.sedaily.com/NewsList/GA","https://www.sedaily.com",["/NewsView/"]),
        lambda: generic("이데일리","https://www.edaily.co.kr/News/Stock","https://www.edaily.co.kr",["/News/Read"]),
        lambda: generic("머니투데이","https://news.mt.co.kr/newsList.html?pDepth1=stock","https://news.mt.co.kr",["/mtview.php","/newsView.html"]),
        lambda: generic("아시아경제","https://www.asiae.co.kr/news/list.htm?sec=eco99","https://www.asiae.co.kr",["/article/"]),
        lambda: generic("파이낸셜뉴스","https://www.fnnews.com/section/002000000","https://www.fnnews.com",["/news/"]),
        lambda: generic("조선비즈","https://biz.chosun.com/stock/","https://biz.chosun.com",["/stock/","/industry/","/it-science/"]),
        lambda: generic("전자신문","https://www.etnews.com/news/section.html?id1=20","https://www.etnews.com",["/news/article.html"]),
        lambda: generic("ZDNet","https://zdnet.co.kr/news/","https://zdnet.co.kr",["/view/"]),
        lambda: generic("디지털데일리","https://www.ddaily.co.kr/","https://www.ddaily.co.kr",["/page/view/"]),
        lambda: generic("연합뉴스","https://www.yna.co.kr/economy/all","https://www.yna.co.kr",["/view/"]),
        lambda: generic("뉴스1","https://www.news1.kr/economy","https://www.news1.kr",["/articles/"]),
        lambda: generic("한국일보","https://www.hankookilbo.com/News/Economy","https://www.hankookilbo.com",["/News/Read"]),
    ]
    out = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for f in as_completed([ex.submit(t) for t in tasks]):
            try: out.extend(f.result())
            except: pass
    return out

def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS news(
        title TEXT, display_title TEXT, sentiment TEXT, company TEXT, theme TEXT,
        media TEXT, display_dt TEXT, sort_ts REAL, stock_related INTEGER,
        dedupe_key TEXT, link TEXT UNIQUE, inserted_at TEXT
    )""")
    con.commit(); con.close()

def save(rows):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    for r in rows:
        cur.execute("""INSERT INTO news VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(link) DO UPDATE SET
        title=excluded.title, display_title=excluded.display_title, sentiment=excluded.sentiment,
        company=excluded.company, theme=excluded.theme, media=excluded.media,
        display_dt=excluded.display_dt, sort_ts=excluded.sort_ts,
        stock_related=excluded.stock_related, dedupe_key=excluded.dedupe_key,
        inserted_at=excluded.inserted_at""",
        (r["title"],r["display_title"],r["sentiment"],r["company"],r["theme"],r["media"],
         r["display_dt"],r["sort_ts"],r["stock_related"],r["dedupe_key"],r["link"],r["inserted_at"]))
    con.commit(); con.close()

def load():
    con = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM news", con)
    con.close()
    if df.empty: return df
    cutoff = (now() - timedelta(hours=KEEP_HOURS)).timestamp()
    df["sort_ts"] = pd.to_numeric(df["sort_ts"], errors="coerce")
    df = df[df["sort_ts"] >= cutoff]
    df = df.sort_values("sort_ts", ascending=False).drop_duplicates("dedupe_key").reset_index(drop=True)
    return df

@st.cache_data(ttl=15)
def refresh():
    init_db()
    save(collect())
    return load()

st.title("📰 뉴스 터미널")
st.caption("15초 자동갱신 | 기사 원문/RSS 절대시간 기준 | 상대시간 제외 | 최근 24시간 | 중복 제거")

if st.button("DB 완전 초기화 / 강제 새로고침"):
    st.cache_data.clear()
    if os.path.exists(DB_PATH): os.remove(DB_PATH)
    st.rerun()

df = refresh()
if df.empty:
    st.warning("뉴스가 없습니다.")
    st.stop()

c0,c1,c2,c3,c4,c5 = st.columns([1,1,1,1,1,2])
with c0: stock_filter = st.selectbox("범위", ["전체","주식관련만"])
with c1: sent_filter = st.selectbox("감성", ["전체","🔵 긍정","⚪ 중립","🔴 부정"])
with c2: comp_filter = st.selectbox("회사명", ["전체"] + sorted(df["company"].unique()))
with c3: theme_filter = st.selectbox("테마", ["전체"] + sorted(df["theme"].unique()))
with c4: media_filter = st.selectbox("매체", ["전체"] + sorted(df["media"].unique()))
with c5: search = st.text_input("검색")

f = df.copy()
if stock_filter == "주식관련만": f = f[f["stock_related"] == 1]
if sent_filter != "전체": f = f[f["sentiment"] == sent_filter]
if comp_filter != "전체": f = f[f["company"] == comp_filter]
if theme_filter != "전체": f = f[f["theme"] == theme_filter]
if media_filter != "전체": f = f[f["media"] == media_filter]
if search:
    f = f[f["title"].str.contains(search, case=False, na=False) | f["company"].str.contains(search, case=False, na=False) | f["theme"].str.contains(search, case=False, na=False)]
f = f.sort_values("sort_ts", ascending=False).reset_index(drop=True)

st.subheader(f"전체 뉴스 {len(f)}개")
with st.expander("매체별 수집 개수 확인"):
    st.dataframe(df.groupby("media").size().reset_index(name="개수").sort_values("개수", ascending=False), use_container_width=True, hide_index=True)

rows = ""
for _, r in f.head(1500).iterrows():
    rows += f"""<tr>
<td class="title"><a href="{html.escape(r['link'])}" target="_blank">{html.escape(r['display_title'])}</a></td>
<td>{html.escape(r['sentiment'])}</td><td>{html.escape(r['company'])}</td>
<td>{html.escape(r['theme'])}</td><td>{html.escape(r['media'])}</td><td>{html.escape(r['display_dt'])}</td>
</tr>"""

components.html(f"""
<style>
table{{width:100%;border-collapse:collapse;font-size:12.5px;table-layout:fixed}}
th{{background:#f1f3f5;padding:7px;border-bottom:1px solid #ddd;text-align:left}}
td{{padding:5px 6px;border-bottom:1px solid #eee;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
tr:hover{{background:#f8f9fa}}
.title{{width:70%;font-weight:600}}
a{{color:#005bac;text-decoration:none}}
a:hover{{text-decoration:underline}}
</style>
<table>
<thead><tr><th class="title">제목</th><th>감성</th><th>회사명</th><th>테마</th><th>매체</th><th>일자</th></tr></thead>
<tbody>{rows}</tbody>
</table>
""", height=850, scrolling=True)
