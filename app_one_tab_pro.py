
import os
import sqlite3
from pathlib import Path
import base64
import pandas as pd
import streamlit as st
import sys
from pathlib import Path

def resource_path(rel: str) -> str:
    return str(Path(__file__).resolve().parent / rel)

@st.cache_data(show_spinner=False)
def load_logo_b64(rel_path: str = ".streamlit/static/assets/logo.jpg") -> str:
    try:
        with open(resource_path(rel_path), "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        st.warning(f"⚠️ لوگو پیدا نشد: {rel_path} — {e}")
        return ""





st.set_page_config(page_title="آرشیو کتاب‌های فنی شرکت خدمات دریایی کاوه", layout="wide")


def inject_global_theme(font_path: str = ".streamlit/static/fonts/IRANSansWeb.woff2"):
    try:
        font_bytes = Path(font_path).read_bytes()
        b64 = base64.b64encode(font_bytes).decode("utf-8")
    except Exception as e:
        b64 = ""
        st.warning(f"⚠️ فونت پیدا نشد: {font_path} — {e}")

    st.markdown(f"""
    <style>
    
    @font-face {{
      font-family: 'IRANSansWeb';
      src: url(data:font/woff2;base64,{b64}) format('woff2');
      font-weight: 300;
      font-style: normal;
      font-display: swap;
    }}
    @font-face {{
      font-family: 'IRANSansWeb';
      src: url(data:font/woff2;base64,{b64}) format('woff2');
      font-weight: 400;
      font-style: normal;
      font-display: swap;
    }}
    @font-face {{
      font-family: 'IRANSansWeb';
      src: url(data:font/woff2;base64,{b64}) format('woff2');
      font-weight: 700;
      font-style: normal;
      font-display: swap;
    }}

    
    :root {{
      --brand-primary: #2563eb;
      --brand-primary-600: #1e4fd8;
      --brand-bg: #f5f7fb;
      --surface: #ffffff;
      --border: #e6eaf2;
      --shadow: 0 10px 24px rgba(15, 23, 42, .06);
      --radius: 16px;
      --radius-sm: 12px;
      --text: #0f172a;
      --text-muted: #475569;
    }}

    
    html, body, .stApp, [data-testid="stAppViewContainer"] * {{
      
      text-align: center ;
      font-family: 'IRANSansWeb', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif !important;
      color: var(--text);
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
    }}

    .stApp {{
      background: linear-gradient(180deg, var(--brand-bg) 0%, #fff 60%);
    }}
    section.main > div.block-container {{
      max-width: 1200px;
      padding-top: .5rem;
      padding-bottom: 2rem;
    }}

    
    h1, h2, h3 {{ letter-spacing: -0.2px; font-weight: 700; color: var(--text); }}
    h1 {{ display:flex; align-items:center; gap:.5rem; margin-bottom:.5rem; }}

    
    .card, .subheader-card, .right-menu {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
    }}
    .subheader-card {{ padding: 12px 16px; margin-bottom: 12px; }}
    .right-menu {{ position: sticky; top: 12px; padding: 12px; ; }}

    
    .stTextInput input,
    .stSelectbox div[data-baseweb="select"] div,
    .stFileUploader>div {{
      
      border-radius: var(--radius-sm) !important;
    }}
    .stTextInput input::placeholder {{ color: #9aa6b2; }}

    .stButton>button, .stDownloadButton>button {{
      background: var(--brand-primary);
      color:#fff; border:none; border-radius:14px;
      padding:.6rem 1.1rem; font-weight:700;
      box-shadow: 0 10px 18px rgba(37,99,235,.18);
      transition: transform .05s ease, background .2s ease;
    }}
    .stButton>button:hover, .stDownloadButton>button:hover {{ background: var(--brand-primary-600); transform: translateY(-1px); }}

    
    div[role="radiogroup"] label p {{ font-weight:600; }}

    
    .stApp .stDataFrame [data-testid="stTable"] thead tr th,
    .stApp .stDataFrame [data-testid="stTable"] tbody tr td {{
      text-align: center !important;   /* وسط */
    }}
    
    
    .stApp [data-testid="stDataFrame"] div[role="columnheader"],
    .stApp [data-testid="stDataFrame"] div[role="gridcell"] {{
      display: flex !important;
      align-items: center !important;
      justify-content: center !important; /* وسط */
      text-align: center !important;
    }}

    
    * {{ scrollbar-width: thin; scrollbar-color: #cbd5e1 transparent; }}
    *::-webkit-scrollbar {{ height: 10px; width: 10px; }}
    *::-webkit-scrollbar-thumb {{
      background: #cbd5e1; border-radius: 12px; border: 2px solid transparent;
      background-clip: padding-box;
    }}
    *::-webkit-scrollbar-thumb:hover {{ background: #94a3b8; }}
    </style>
    """, unsafe_allow_html=True)


inject_global_theme(resource_path(".streamlit/static/fonts/IRANSansWeb.woff2"))

DEFAULT_DB = "books_archive.db"
SHEET_NAME = "آرشیو کتاب‌ها"

COLUMN_MAP = {
    'شماره کتاب': 'book_id',
    'برند ماشین‌آلات': 'brand',
    'مدل ماشین‌آلات': 'model',
    'نوع ماشین‌آلات': 'machine_type',
    'عنوان کتاب': 'title',
    'زبان کتاب': 'language',
    'سال چاپ / ورژن': 'edition_year',
    'محل نگهداری': 'location'
}

SCHEMA = '''
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS brands (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS machine_types (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS models (id INTEGER PRIMARY KEY, name TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS languages (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY,
    book_id INTEGER UNIQUE NOT NULL,
    title TEXT NOT NULL,
    edition_year TEXT,
    location TEXT,
    brand_id INTEGER,
    model_id INTEGER,
    machine_type_id INTEGER,
    language_id INTEGER,
    FOREIGN KEY (brand_id) REFERENCES brands(id),
    FOREIGN KEY (model_id) REFERENCES models(id),
    FOREIGN KEY (machine_type_id) REFERENCES machine_types(id),
    FOREIGN KEY (language_id) REFERENCES languages(id)
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
'''

def load_excel_to_df(xl_bytes):
    import io
    df = pd.read_excel(io.BytesIO(xl_bytes), sheet_name=SHEET_NAME)
    df = df.rename(columns=COLUMN_MAP)
    for col in ['brand','model','machine_type','title','language']:
        df[col] = df[col].astype(str).str.strip()
        df[col] = df[col].replace({'nan': pd.NA})
    df['language'] = df['language'].fillna('Unknown')
    return df

def create_schema(conn, drop=False):
    cur = conn.cursor()
    if drop:
        cur.executescript('''
        DROP TABLE IF EXISTS books;
        DROP TABLE IF EXISTS brands;
        DROP TABLE IF EXISTS models;
        DROP TABLE IF EXISTS machine_types;
        DROP TABLE IF EXISTS languages;
        DROP TABLE IF EXISTS meta;
        ''')
    cur.executescript(SCHEMA)
    conn.commit()

def get_id(cur, table, name):
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return None
    cur.execute(f"INSERT OR IGNORE INTO {table} (name) VALUES (?)", (name,))
    cur.execute(f"SELECT id FROM {table} WHERE name=?", (name,))
    row = cur.fetchone()
    return row[0] if row else None

def populate_replace(conn, df):
    create_schema(conn, drop=True)
    cur = conn.cursor()
    for t, col in [('brands','brand'), ('machine_types','machine_type'),
                   ('models','model'), ('languages','language')]:
        for v in sorted(df[col].dropna().unique()):
            get_id(cur, t, v)
    conn.commit()
    for _, r in df.iterrows():
        brand_id = get_id(cur, 'brands', r['brand']) if pd.notna(r['brand']) else None
        mtype_id = get_id(cur, 'machine_types', r['machine_type']) if pd.notna(r['machine_type']) else None
        model_id = get_id(cur, 'models', r['model']) if pd.notna(r['model']) else None
        lang_id  = get_id(cur, 'languages', r['language']) if pd.notna(r['language']) else None
        cur.execute('''
            INSERT INTO books (book_id, title, edition_year, location, brand_id, model_id, machine_type_id, language_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (int(r['book_id']), r['title'],
              None if pd.isna(r.get('edition_year')) else str(r['edition_year']),
              None if pd.isna(r.get('location')) else str(r['location']),
              brand_id, model_id, mtype_id, lang_id))
    conn.commit()

def load_db_to_df(db_path):
    conn = sqlite3.connect(db_path)
    dfb = pd.read_sql_query('''
        SELECT b.book_id AS "شماره",
               b.title     AS "عنوان",
               br.name     AS "برند",
               m.name      AS "مدل",
               mt.name     AS "نوع ماشین‌آلات",
               lg.name     AS "زبان",
               b.edition_year AS "سال/ورژن",
               b.location  AS "محل نگهداری"
        FROM books b
        LEFT JOIN brands br ON b.brand_id = br.id
        LEFT JOIN models m ON b.model_id = m.id
        LEFT JOIN machine_types mt ON b.machine_type_id = mt.id
        LEFT JOIN languages lg ON b.language_id = lg.id
        ORDER BY b.book_id
    ''', conn)
    conn.close()
    return dfb


if "db_path" not in st.session_state:
    st.session_state["db_path"] = "books_archive.db"
if "df" not in st.session_state:
    st.session_state["df"] = None




logo_b64 = load_logo_b64()  # اگر مسیر دیگری داری: load_logo_b64("path/to/logo.png")

st.markdown(f"""
<div class="subheader-card" style="display:flex; align-items:center; gap:12px;">
  {'<img src="data:image/jpeg;base64,' + logo_b64 + '" style="height:52px; width:auto;" alt="لوگو">' if logo_b64 else ''}
  <h2 style="margin:0;">📘 آرشیو کتاب‌های فنی شرکت خدمات دریایی و بندری کاوه</h2>
</div>
""", unsafe_allow_html=True)

exists = os.path.exists(st.session_state["db_path"])

main_col, menu_col = st.columns([5, 1], gap="large")

with menu_col:
    st.markdown('<div class="subheader-card"><h4>منو</h4></div>', unsafe_allow_html=True)
    menu = st.radio(" ", options=["📚 آرشیو کتاب‌ها", "🔄 آپدیت آرشیو"], label_visibility="collapsed", index=0)
    st.markdown('</div>', unsafe_allow_html=True)

with main_col:
    if menu == "📚 آرشیو کتاب‌ها":
        st.markdown('<div class="subheader-card"><h4>مرور آرشیو</h4></div>', unsafe_allow_html=True)

        if exists:
            if st.session_state["df"] is None:
                try:
                    st.session_state["df"] = load_db_to_df(st.session_state["db_path"])
                except Exception as e:
                    st.error(f"خطا در خواندن دیتابیس: {e}")

            dfb = st.session_state["df"]
            if dfb is not None:
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    f_brand = st.selectbox("برند", ["(همه)"] + sorted([x for x in dfb["برند"].dropna().unique()]), key="f_brand")
                with c2:
                    f_type = st.selectbox("نوع", ["(همه)"] + sorted([x for x in dfb["نوع ماشین‌آلات"].dropna().unique()]), key="f_type")
                with c3:
                    f_model = st.selectbox("مدل", ["(همه)"] + sorted([x for x in dfb["مدل"].dropna().unique()]), key="f_model")
                with c4:
                    f_lang = st.selectbox("زبان", ["(همه)"] + sorted([x for x in dfb["زبان"].dropna().unique()]), key="f_lang")

                q = st.text_input("جستجو در عنوان", key="q_title")

                filt = dfb.copy()
                if f_brand != "(همه)": filt = filt[filt["برند"] == f_brand]
                if f_type  != "(همه)": filt = filt[filt["نوع ماشین‌آلات"] == f_type]
                if f_model != "(همه)": filt = filt[filt["مدل"] == f_model]
                if f_lang  != "(همه)":  filt = filt[filt["زبان"] == f_lang]
                if q: filt = filt[filt["عنوان"].str.contains(q, case=False, na=False)]

                st.caption(f"تعداد نتایج: {len(filt)}")
                st.dataframe(filt, use_container_width=True)
            else:
                st.info("دیتابیس بارگذاری نشد. به «آپدیت آرشیو» بروید و از اکسل بسازید/به‌روزرسانی کنید.")
        else:
            st.warning("⚠️ دیتابیس پیدا نشد. به منوی «🔄 آپدیت آرشیو» بروید و دیتابیس را از اکسل بسازید.")

    else:
        st.markdown('<div class="subheader-card"><h4>آپدیت/ایجاد دیتابیس از اکسل</h4></div>', unsafe_allow_html=True)

        uploaded = st.file_uploader("آپلود اکسل (شیت: «آرشیو کتاب‌ها»)", type=["xlsx"], key="xl_up")
        disabled_btn = uploaded is None
        if st.button("🔄 به‌روزرسانی دیتابیس از اکسل (بازسازی کامل)", type="primary", disabled=disabled_btn, use_container_width=True):
            if uploaded is None:
                st.warning("ابتدا فایل اکسل را انتخاب کنید.")
            else:
                try:
                    df_excel = load_excel_to_df(uploaded.getvalue())
                    conn = sqlite3.connect(st.session_state["db_path"])
                    populate_replace(conn, df_excel)  # always replace
                    conn.close()
                    st.session_state["df"] = load_db_to_df(st.session_state["db_path"])
                    st.success("✅ دیتابیس با موفقیت بازسازی شد.")
                except Exception as e:
                    st.error(f"خطا در تبدیل اکسل به دیتابیس: {e}")

        if exists:
            st.caption(f"مسیر دیتابیس فعلی: `{st.session_state['db_path']}`")
        else:
            st.info("هنوز دیتابیسی در مسیر فعلی وجود ندارد. با آپلود اکسل و زدن دکمه بالا ایجاد خواهد شد.")
