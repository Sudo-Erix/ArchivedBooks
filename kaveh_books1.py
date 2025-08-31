#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kaveh Books Archive — Desktop GUI (PySide6)
نسخه‌ی بازنگری‌شده با نمایش عالی برای عنوان‌های بلند + تغییر اندازه‌ی دستی ستون‌ها
--------------------------------------------------------------------------
- ظاهر حرفه‌ای، راست‌به‌چپ، فونت فارسی سفارشی
- جدول با:
  • ستون‌ها قابل تغییر اندازه با ماوس (Interactive)
  • «عنوان» چندخطی با ارتفاع سطر خودکار
  • دکمه‌ی «متناسب‌سازی هوشمند ستون‌ها با محتوا» (Auto-Fit)
  • ذخیره/بازیابی اندازه‌ی ستون‌ها بین اجراها (QSettings)
- هم‌خوان با همان شِما/ستون‌ها/شیت اکسل اپ Streamlit شما

نیازمندی‌ها:
  pip install PySide6 pandas openpyxl

بسته‌بندی (مثال PyInstaller):
  pyinstaller --noconfirm --windowed --onefile     --add-data "assets/fonts/IRANSans.ttf:assets/fonts"     --add-data "assets/logo.jpg:assets"     kaveh_books1.py
"""
import os
import sys
import sqlite3
from pathlib import Path
from typing import Optional, Set

import pandas as pd

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSize, QSettings
from PySide6.QtGui import QFont, QIcon, QAction, QFontDatabase, QTextDocument
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFileDialog, QMessageBox,
    QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit, QPushButton,
    QTableView, QHeaderView, QGroupBox, QSplitter, QSizePolicy, QStatusBar,
    QStyledItemDelegate, QStyleOptionViewItem, QStyle
)

APP_NAME = "آرشیو کتاب‌های فنی کاوه"
ORG_NAME = "KavehCo"
APP_KEY  = "KavehBooksDesktop"

DEFAULT_DB = "books_archive.db"
SHEET_NAME = "آرشیو کتاب‌ها"  # همان شیت استریم‌لیت

# نگاشت ستون‌ها دقیقاً مطابق اپ Streamlit
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

# اسکیمای دیتابیس (همان)
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

# ستون‌های نمایشی فارسی (مطابق Query اپ شما)
DISPLAY_COLUMNS = [
    "شماره", "عنوان", "برند", "مدل", "نوع ماشین‌آلات", "زبان", "سال/ورژن", "محل نگهداری"
]

ASSETS_DIR = Path("assets")
FONT_PATH = ASSETS_DIR / "fonts/IRANSansX-Regular.ttf"  # می‌توانید Vazirmatn را جایگزین کنید
LOGO_PATH = ASSETS_DIR / "logo.jpg"

# -------------------- Utils --------------------
def resource_path(rel: str) -> str:
    try:
        base = Path(sys._MEIPASS)  # PyInstaller
    except Exception:
        base = Path(__file__).resolve().parent
    return str((base / rel).resolve())


def ensure_dirs():
    (ASSETS_DIR / "fonts").mkdir(parents=True, exist_ok=True)


def load_persian_font() -> Optional[str]:
    try:
        fpath = Path(resource_path(str(FONT_PATH)))
        if fpath.exists():
            fid = QFontDatabase.addApplicationFont(str(fpath))
            fams = QFontDatabase.applicationFontFamilies(fid)
            if fams:
                return fams[0]
    except Exception:
        pass
    return None

# ----------------- DB Helpers -----------------

def create_schema(conn: sqlite3.Connection, drop: bool = False):
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


def get_id(cur: sqlite3.Cursor, table: str, name: Optional[str]):
    if not name or (isinstance(name, float) and pd.isna(name)):
        return None
    cur.execute(f"INSERT OR IGNORE INTO {table} (name) VALUES (?)", (name,))
    cur.execute(f"SELECT id FROM {table} WHERE name=?", (name,))
    row = cur.fetchone()
    return row[0] if row else None


def load_excel_to_df(xl_path: str) -> pd.DataFrame:
    df = pd.read_excel(xl_path, sheet_name=SHEET_NAME)
    df = df.rename(columns=COLUMN_MAP)
    for col in ['brand', 'model', 'machine_type', 'title', 'language']:
        df[col] = df[col].astype(str).str.strip()
        df[col] = df[col].replace({'nan': pd.NA})
    df['language'] = df['language'].fillna('Unknown')
    return df


def populate_replace(conn: sqlite3.Connection, df: pd.DataFrame):
    create_schema(conn, drop=True)
    cur = conn.cursor()
    # بارگذاری اولیه جداول بُعدی
    for t, col in [('brands', 'brand'), ('machine_types', 'machine_type'),
                   ('models', 'model'), ('languages', 'language')]:
        for v in sorted(df[col].dropna().unique()):
            get_id(cur, t, v)
    conn.commit()
    # درج کتاب‌ها
    for _, r in df.iterrows():
        brand_id = get_id(cur, 'brands', r['brand']) if pd.notna(r['brand']) else None
        mtype_id = get_id(cur, 'machine_types', r['machine_type']) if pd.notna(r['machine_type']) else None
        model_id = get_id(cur, 'models', r['model']) if pd.notna(r['model']) else None
        lang_id  = get_id(cur, 'languages', r['language']) if pd.notna(r['language']) else None
        cur.execute('''
            INSERT INTO books (book_id, title, edition_year, location, brand_id, model_id, machine_type_id, language_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            int(r['book_id']), r['title'],
            None if pd.isna(r.get('edition_year')) else str(r['edition_year']),
            None if pd.isna(r.get('location')) else str(r['location']),
            brand_id, model_id, mtype_id, lang_id
        ))
    conn.commit()


def load_db_to_df(db_path: str) -> pd.DataFrame:
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

# ----------------- Qt Model -----------------
class DataFrameModel(QAbstractTableModel):
    def __init__(self, df: pd.DataFrame):
        super().__init__()
        self._df = df.copy()

    def set_dataframe(self, df: pd.DataFrame):
        self.beginResetModel()
        self._df = df.copy()
        self.endResetModel()

    def dataframe(self) -> pd.DataFrame:
        return self._df

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._df)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._df.columns)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        val = self._df.iat[index.row(), index.column()]
        if role in (Qt.DisplayRole, Qt.EditRole):
            return "" if pd.isna(val) else str(val)
        if role == Qt.TextAlignmentRole:
            return int(Qt.AlignCenter)
        if role == Qt.ToolTipRole:
            s = "" if pd.isna(val) else str(val)
            return s if len(s) > 40 else None
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            try:
                return str(self._df.columns[section])
            except Exception:
                return ""
        return str(section + 1)

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemIsEnabled
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

# ----------------- Word-Wrap Delegate -----------------
class WordWrapDelegate(QStyledItemDelegate):
    """نمایش چندخطی برای ستون‌های تعیین‌شده (مثل «عنوان») با ارتفاع سطر خودکار."""
    def __init__(self, wrap_columns: Set[int], parent=None):
        super().__init__(parent)
        self.wrap_columns = set(wrap_columns)

    def paint(self, painter, option: QStyleOptionViewItem, index: QModelIndex):
        if index.column() in self.wrap_columns:
            opt = QStyleOptionViewItem(option)
            self.initStyleOption(opt, index)
            opt.textElideMode = Qt.ElideNone
            opt.features |= QStyleOptionViewItem.WrapText
            style = opt.widget.style() if opt.widget else QApplication.style()
            style.drawControl(QStyle.CE_ItemViewItem, opt, painter)
        else:
            super().paint(painter, option, index)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        if index.column() in self.wrap_columns:
            opt = QStyleOptionViewItem(option)
            self.initStyleOption(opt, index)
            text = opt.text
            # عرض مؤثرِ متن؛ اگر هنوز صفر است، یک مقدار پیش‌فرض بده
            width = max(option.rect.width(), 360)
            doc = QTextDocument()
            doc.setDefaultFont(opt.font)
            doc.setTextWidth(width)
            doc.setPlainText(text)
            h = int(doc.size().height()) + 12  # کمی پدینگ
            return QSize(int(doc.idealWidth()), h)
        return super().sizeHint(option, index)

# ----------------- Main Window -----------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1200, 740)
        self.setMinimumSize(980, 600)

        self.settings = QSettings(ORG_NAME, APP_KEY)
        self._db_path = DEFAULT_DB
        self._df_full = pd.DataFrame(columns=DISPLAY_COLUMNS)
        self._wrap_enabled = True

        # RTL + Font
        QApplication.instance().setLayoutDirection(Qt.RightToLeft)
        fam = load_persian_font()
        base_font = QFont(fam if fam else QApplication.font().family(), 10)
        QApplication.instance().setFont(base_font)

        # Stylesheet
        self.setStyleSheet(self._app_stylesheet())

        # UI
        self._build_ui()
        self._load_db_if_exists()
        self._update_filters()
        self.apply_filters()

        # Status bar
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("آماده")

        # Menus
        self._build_menu()

        # Restore window & columns
        self._restore_window_state()

    # ---------- UI Build ----------
    def _build_ui(self):
        banner = self._banner_widget()
        filters = self._filters_panel()

        self.table = QTableView()
        self.model = DataFrameModel(self._df_full)
        self.table.setModel(self.model)

        # جدول: رفتار اندازه‌ی ستون‌ها
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.Interactive)   # تغییر اندازه دستی با ماوس
        h.setStretchLastSection(False)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(True)
        self.table.setTextElideMode(Qt.ElideNone)
        self.table.setSortingEnabled(True)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # ارتفاع سطرها بر اساس محتوا (ویژه‌ی ستون «عنوان»)
        v = self.table.verticalHeader()
        v.setSectionResizeMode(QHeaderView.ResizeToContents)

        # Delegate برای چندخطیِ ستون عنوان
        self._apply_wrap_delegate()

        # Layout
        right = QWidget()
        right_l = QVBoxLayout(right)
        right_l.addWidget(banner)
        right_l.addWidget(self.table)

        split = QSplitter()
        split.addWidget(filters)
        split.addWidget(right)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)

        cw = QWidget()
        cwl = QVBoxLayout(cw)
        cwl.addWidget(split)
        self.setCentralWidget(cw)

    def _build_menu(self):
        m = self.menuBar()
        file_menu = m.addMenu("فایل")
        act_open_excel = QAction("بازسازی از اکسل…", self)
        act_open_excel.triggered.connect(self.action_rebuild_from_excel)
        file_menu.addAction(act_open_excel)

        act_export_csv = QAction("خروجی CSV از نتایج", self)
        act_export_csv.triggered.connect(self.action_export_csv)
        file_menu.addAction(act_export_csv)

        file_menu.addSeparator()
        act_choose_db = QAction("انتخاب دیتابیس…", self)
        act_choose_db.triggered.connect(self.action_choose_db)
        file_menu.addAction(act_choose_db)

        file_menu.addSeparator()
        act_exit = QAction("خروج", self)
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        view_menu = m.addMenu("نمایش")
        self.act_wrap = QAction("نمایش عناوین چندخطی", self, checkable=True, checked=self._wrap_enabled)
        self.act_wrap.triggered.connect(self.toggle_wrap)
        view_menu.addAction(self.act_wrap)

        act_fit = QAction("متناسب‌سازی هوشمند ستون‌ها با محتوا", self)
        act_fit.triggered.connect(self.smart_autofit_columns)
        view_menu.addAction(act_fit)

        act_reset = QAction("بازنشانی اندازه ستون‌ها", self)
        act_reset.triggered.connect(self.reset_columns_default)
        view_menu.addAction(act_reset)

    def _banner_widget(self) -> QWidget:
        w = QWidget()
        l = QHBoxLayout(w)
        l.setContentsMargins(12, 12, 12, 12)

        logo_lbl = QLabel()
        logo_path = Path(resource_path(str(LOGO_PATH)))
        if logo_path.exists():
            logo_lbl.setPixmap(QIcon(str(logo_path)).pixmap(48, 48))
        title = QLabel("📘 آرشیو کتاب‌های فنی شرکت خدمات دریایی و بندری کاوه")
        title.setObjectName("HeaderTitle")
        l.addWidget(logo_lbl)
        l.addWidget(title)
        l.addStretch(1)

        self.count_lbl = QLabel("تعداد نتایج: 0")
        self.count_lbl.setObjectName("CountLabel")
        l.addWidget(self.count_lbl)
        return w

    def _filters_panel(self) -> QWidget:
        g = QGroupBox("مرور و فیلتر")
        g.setObjectName("Card")
        lay = QVBoxLayout(g)

        self.brand_cmb = QComboBox(); self.type_cmb = QComboBox(); self.model_cmb = QComboBox(); self.lang_cmb = QComboBox()
        for cmb in (self.brand_cmb, self.type_cmb, self.model_cmb, self.lang_cmb):
            cmb.setEditable(False)

        self.search_edt = QLineEdit(); self.search_edt.setPlaceholderText("جستجو در عنوان…")

        btn_apply = QPushButton("اعمال فیلترها"); btn_clear = QPushButton("پاک‌سازی")
        btn_apply.clicked.connect(self.apply_filters)
        btn_clear.clicked.connect(self.clear_filters)

        lay.addWidget(QLabel("برند")); lay.addWidget(self.brand_cmb)
        lay.addWidget(QLabel("نوع ماشین‌آلات")); lay.addWidget(self.type_cmb)
        lay.addWidget(QLabel("مدل")); lay.addWidget(self.model_cmb)
        lay.addWidget(QLabel("زبان")); lay.addWidget(self.lang_cmb)
        lay.addWidget(QLabel("جستجو در عنوان")); lay.addWidget(self.search_edt)

        lay.addSpacing(6)
        row = QWidget(); row_l = QHBoxLayout(row); row_l.setContentsMargins(0, 0, 0, 0)
        row_l.addWidget(btn_apply); row_l.addWidget(btn_clear)
        lay.addWidget(row)
        lay.addStretch(1)

        # Auto-apply
        self.brand_cmb.currentIndexChanged.connect(self.apply_filters)
        self.type_cmb.currentIndexChanged.connect(self.apply_filters)
        self.model_cmb.currentIndexChanged.connect(self.apply_filters)
        self.lang_cmb.currentIndexChanged.connect(self.apply_filters)
        self.search_edt.textChanged.connect(self.apply_filters)

        return g

    # ---------- Data / Filters ----------
    def _load_db_if_exists(self):
        if Path(self._db_path).exists():
            try:
                self._df_full = load_db_to_df(self._db_path)
                self.model.set_dataframe(self._df_full)
                self.statusBar().showMessage(f"دیتابیس خوانده شد: {self._db_path}")
            except Exception as e:
                QMessageBox.critical(self, APP_NAME, f"خطا در خواندن دیتابیس:{e}")
        else:
            self.statusBar().showMessage("دیتابیس پیدا نشد. از منوی فایل → بازسازی از اکسل استفاده کنید.")

    def _update_filters(self):
        df = self._df_full
        def opts(series):
            vals = sorted([x for x in series.dropna().unique()])
            return ["(همه)"] + vals
        if not df.empty:
            self._fill_combo(self.brand_cmb, opts(df["برند"]))
            self._fill_combo(self.type_cmb, opts(df["نوع ماشین‌آلات"]))
            self._fill_combo(self.model_cmb, opts(df["مدل"]))
            self._fill_combo(self.lang_cmb, opts(df["زبان"]))
        else:
            for cmb in (self.brand_cmb, self.type_cmb, self.model_cmb, self.lang_cmb):
                self._fill_combo(cmb, ["(همه)"])

    @staticmethod
    def _fill_combo(cmb: QComboBox, items):
        cmb.blockSignals(True); cmb.clear(); cmb.addItems(items); cmb.setCurrentIndex(0); cmb.blockSignals(False)

    def clear_filters(self):
        for cmb in (self.brand_cmb, self.type_cmb, self.model_cmb, self.lang_cmb):
            cmb.setCurrentIndex(0)
        self.search_edt.clear()
        self.apply_filters()

    def apply_filters(self):
        df = self._df_full.copy()
        f_brand = self.brand_cmb.currentText(); f_type = self.type_cmb.currentText()
        f_model = self.model_cmb.currentText(); f_lang = self.lang_cmb.currentText()
        q = self.search_edt.text().strip()

        if not df.empty:
            if f_brand and f_brand != "(همه)": df = df[df["برند"] == f_brand]
            if f_type and f_type != "(همه)": df = df[df["نوع ماشین‌آلات"] == f_type]
            if f_model and f_model != "(همه)": df = df[df["مدل"] == f_model]
            if f_lang and f_lang != "(همه)": df = df[df["زبان"] == f_lang]
            if q: df = df[df["عنوان"].astype(str).str.contains(q, case=False, na=False)]

        self.count_lbl.setText(f"تعداد نتایج: {len(df)}")
        self.model.set_dataframe(df)

        # بعد از هر تغییری، تناسب ستون‌ها و ارتفاع سطرها را بده
        self.smart_autofit_columns()

    # ---------- Actions ----------
    def action_rebuild_from_excel(self):
        xlsx, _ = QFileDialog.getOpenFileName(self, "انتخاب فایل اکسل", "", "Excel Files (*.xlsx)")
        if not xlsx:
            return
        try:
            df = load_excel_to_df(xlsx)
            conn = sqlite3.connect(self._db_path)
            populate_replace(conn, df)
            conn.close()
            self._df_full = load_db_to_df(self._db_path)
            self.model.set_dataframe(self._df_full)
            self._update_filters(); self.apply_filters()
            QMessageBox.information(self, APP_NAME, "✅ دیتابیس با موفقیت بازسازی شد.")
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, f"خطا در تبدیل اکسل به دیتابیس:{e}")

    def action_export_csv(self):
        if self.model.dataframe().empty:
            QMessageBox.information(self, APP_NAME, "جدولی برای خروجی وجود ندارد.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "ذخیره CSV", "results.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            self.model.dataframe().to_csv(path, index=False, encoding='utf-8-sig')
            QMessageBox.information(self, APP_NAME, "فایل CSV با موفقیت ذخیره شد.")
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, f"خطا در ذخیره فایل:{e}")

    def action_choose_db(self):
        db, _ = QFileDialog.getOpenFileName(self, "انتخاب فایل دیتابیس", "", "SQLite DB (*.db)")
        if not db:
            return
        self._db_path = db
        self._load_db_if_exists(); self._update_filters(); self.apply_filters()

    # ---------- Column Fit / Wrap ----------
    def toggle_wrap(self, checked: bool):
        self._wrap_enabled = checked
        self._apply_wrap_delegate()
        # تغییر wrap نیاز به بازسایز ردیف‌ها دارد
        self.smart_autofit_columns()

    def _apply_wrap_delegate(self):
        title_idx = DISPLAY_COLUMNS.index("عنوان") if "عنوان" in DISPLAY_COLUMNS else 1
        if self._wrap_enabled:
            self.table.setItemDelegateForColumn(title_idx, WordWrapDelegate({title_idx}, self.table))
        else:
            self.table.setItemDelegateForColumn(title_idx, QStyledItemDelegate(self.table))

    def smart_autofit_columns(self):
        """ستون‌ها را بر اساس محتوای نمونه‌ای از ردیف‌ها اندازه می‌کند و ردیف‌ها را هم تنظیم می‌کند.
        - ستون «عنوان»: بازه‌ی بزرگ‌تر و چندخطی
        - بقیه ستون‌ها: اندازه‌ی معقول با سقف
        """
        df = self.model.dataframe()
        if df is None or df.empty:
            return
        self.table.setUpdatesEnabled(False)
        fm = self.table.fontMetrics()
        h = self.table.horizontalHeader()

        # پارامترها
        sample_rows = min(800, len(df))
        padding = 28
        title_idx = DISPLAY_COLUMNS.index("عنوان") if "عنوان" in DISPLAY_COLUMNS else 1

        for col in range(len(DISPLAY_COLUMNS)):
            header_text = str(self.model.headerData(col, Qt.Horizontal, Qt.DisplayRole) or "")
            maxw = fm.horizontalAdvance(header_text) + padding
            # نمونه‌گیری برای عملکرد بهتر
            series = df.iloc[:sample_rows, col].astype(str)
            # برای عنوان، عرض خیلی بلند باعث اسکرول افقی می‌شود؛ محدود کنیم
            if col == title_idx:
                # برای عنوان فقط چند نمونه‌ی بلند را بررسی کن
                samples = series.sort_values(key=lambda s: s.str.len(), ascending=False).head(50)
            else:
                samples = series.head(sample_rows)
            for s in samples:
                maxw = max(maxw, fm.horizontalAdvance(s) + padding)

            name = DISPLAY_COLUMNS[col]
            if col == title_idx:
                minw, cap = 280, 780
            elif name in ("محل نگهداری",):
                minw, cap = 140, 360
            else:
                minw, cap = 110, 320

            width = max(minw, min(maxw, cap))
            h.resizeSection(col, int(width))

        # ارتفاع سطرها با محتوای چندخطی هماهنگ شود
        self.table.resizeRowsToContents()
        self.table.setUpdatesEnabled(True)

        # ذخیره اندازه‌ها
        self._save_header_state()

    def reset_columns_default(self):
        self.table.horizontalHeader().reset()
        # دوباره interactive کنیم
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.smart_autofit_columns()

    # ---------- Window/State ----------
    def closeEvent(self, event):
        self._save_window_state()
        super().closeEvent(event)

    def _save_window_state(self):
        self.settings.beginGroup("window")
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.endGroup()
        self._save_header_state()

    def _restore_window_state(self):
        self.settings.beginGroup("window")
        geo = self.settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        self.settings.endGroup()
        self._restore_header_state()

    def _save_header_state(self):
        self.settings.beginGroup("table")
        self.settings.setValue("header", self.table.horizontalHeader().saveState())
        self.settings.endGroup()

    def _restore_header_state(self):
        self.settings.beginGroup("table")
        state = self.settings.value("header")
        if state is not None:
            self.table.horizontalHeader().restoreState(state)
        self.settings.endGroup()

    # ---------- Styles ----------
    @staticmethod
    def _app_stylesheet() -> str:
        return """
        QMainWindow, QWidget { background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #f5f7fb, stop:0.6 #ffffff); color: #0f172a; }
        QGroupBox#Card { background: #ffffff; border: 1px solid #e6eaf2; border-radius: 16px; padding: 12px; }
        QLabel#HeaderTitle { font-weight: 700; font-size: 18px; }
        QLabel#CountLabel { color: #475569; }
        QLineEdit, QComboBox { border: 1px solid #e6eaf2; border-radius: 12px; padding: 8px 10px; }
        QLineEdit:focus, QComboBox:focus { border-color: #2563eb; }
        QPushButton { background: #2563eb; color: white; border: none; border-radius: 14px; padding: 10px 16px; font-weight: 700; }
        QPushButton:hover { background: #1e4fd8; }
        QTableView { background: #fff; gridline-color: #e6eaf2; alternate-background-color: #f9fbff; border: 1px solid #e6eaf2; border-radius: 12px; }
        QHeaderView::section { background: #f1f5ff; padding: 8px; border: none; border-right: 1px solid #e6eaf2; }
        QStatusBar { background: transparent; }
        """

# ----------------- Entrypoint -----------------
def main():
    ensure_dirs()
    app = QApplication(sys.argv)
    app.setOrganizationName(ORG_NAME)
    app.setApplicationName(APP_KEY)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
