#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import shutil
import sqlite3
import threading
import time
import hashlib
from pathlib import Path
from typing import Optional, Set, List, Dict, Tuple, Any
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from collections import defaultdict

import pandas as pd
import numpy as np
from PIL import Image

from PySide6.QtCore import (Qt, QAbstractTableModel, QModelIndex, QSize, QSettings, QTimer, Signal, Slot, QRect, QPoint,
    QThread, QObject, QMutex, QWaitCondition, QRunnable, QThreadPool, QMetaObject, QStandardPaths)
from PySide6.QtGui import (QFont, QIcon, QAction, QFontDatabase, QTextDocument, QPixmap, QImage,
                           QPainter, QColor, QPen, QBrush, QLinearGradient, QMouseEvent, QCursor,
                           QKeySequence, QShortcut, QMovie)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFileDialog, QMessageBox,
    QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit, QPushButton,
    QTableView, QHeaderView, QGroupBox, QSplitter, QSizePolicy, QStatusBar,
    QStyledItemDelegate, QStyleOptionViewItem, QStyle, QGridLayout, QScrollArea,
    QFrame, QStackedWidget, QToolButton, QDialog, QGraphicsDropShadowEffect,
    QSpacerItem, QProgressBar, QProgressDialog, QAbstractItemView,
    QStyleFactory, QDialogButtonBox
)

APP_NAME = "آرشیو کتاب‌های فنی کاوه"
ORG_NAME = "KavehCo"
APP_KEY = "KavehBooksDesktop"
APP_DATA_DIR = Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation))
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_DB_PATH = APP_DATA_DIR / "books_archive.db"
DEFAULT_DB = str(DEFAULT_DB_PATH)
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

OPTIMIZED_SCHEMA = '''
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA cache_size = -2000;

CREATE TABLE IF NOT EXISTS brands (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_brands_name ON brands(name);

CREATE TABLE IF NOT EXISTS machine_types (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_machine_types_name ON machine_types(name);

CREATE TABLE IF NOT EXISTS models (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_models_name ON models(name);

CREATE TABLE IF NOT EXISTS languages (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_languages_name ON languages(name);

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
CREATE INDEX IF NOT EXISTS idx_books_book_id ON books(book_id);
CREATE INDEX IF NOT EXISTS idx_books_title ON books(title);
CREATE INDEX IF NOT EXISTS idx_books_brand_id ON books(brand_id);
CREATE INDEX IF NOT EXISTS idx_books_model_id ON books(model_id);
CREATE INDEX IF NOT EXISTS idx_books_machine_type_id ON books(machine_type_id);
CREATE INDEX IF NOT EXISTS idx_books_language_id ON books(language_id);
CREATE INDEX IF NOT EXISTS idx_books_combined ON books(brand_id, model_id, machine_type_id, language_id);

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
'''

DISPLAY_COLUMNS = [
    "تصویر", "شماره", "عنوان", "برند", "مدل", "نوع ماشین‌آلات", "زبان", "سال/ورژن", "محل نگهداری"
]

ASSETS_DIR = Path("assets")
FONT_PATH = ASSETS_DIR / "fonts/IRANSansX-Regular.ttf"
LOGO_PATH = ASSETS_DIR / "logo.jpg"
PICS_DIR = APP_DATA_DIR / "pics"
CACHE_DIR = APP_DATA_DIR / "cache"
THUMBNAIL_DIR = CACHE_DIR / "thumbnails"
IMAGE_CACHE = {}
THUMBNAIL_CACHE = {}
BOOK_IMAGES_CACHE = {}

class ImageCache:
    """کلاس مدیریت کش تصاویر"""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init_cache()
            return cls._instance

    def _init_cache(self):
        self.full_images = {}
        self.thumbnails = {}
        self.book_images = defaultdict(list)
        self.lru_queue = []
        self.max_cache_size = 500


        THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)

    def get_book_images(self, book_id: str) -> List[str]:
        if book_id not in self.book_images:
            return []
        return self.book_images[book_id]

    def set_book_images(self, book_id: str, images: List[str]):
        self.book_images[book_id] = images

    def get_thumbnail(self, image_path: str, size: Tuple[int, int] = (240, 140)) -> Optional[QPixmap]:
        key = f"{image_path}_{size[0]}_{size[1]}"

        if key in self.thumbnails:
            self.lru_queue.remove(key)
            self.lru_queue.append(key)
            return self.thumbnails[key]

        thumbnail = self._create_thumbnail(image_path, size)
        if thumbnail:
            self.thumbnails[key] = thumbnail
            self.lru_queue.append(key)
            if len(self.thumbnails) > self.max_cache_size:
                oldest_key = self.lru_queue.pop(0)
                del self.thumbnails[oldest_key]

            return thumbnail

        return None

    def _create_thumbnail(self, image_path: str, size: Tuple[int, int]) -> Optional[QPixmap]:
        try:
            key = hashlib.md5(f"{image_path}|{size[0]}x{size[1]}".encode("utf-8")).hexdigest()
            thumb_path = THUMBNAIL_DIR / f"{key}.png"

            if thumb_path.exists():
                pixmap = QPixmap(str(thumb_path))
                if not pixmap.isNull():
                    return pixmap
            img = Image.open(image_path)
            if img.mode in ('RGBA', 'LA'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else img)
                img = background

            img.thumbnail(size, Image.Resampling.LANCZOS)
            img.save(str(thumb_path), 'PNG', optimize=True)
            pixmap = QPixmap(str(thumb_path))
            return pixmap

        except Exception as e:
            print(f"خطا در ایجاد تامبنیل: {e}")
            return None


image_cache = ImageCache()


def resource_path(rel: str) -> str:
    try:
        base_path = Path(sys._MEIPASS)
    except AttributeError:
        base_path = Path(__file__).resolve().parent

    abs_path = base_path / rel

    if not abs_path.exists():
        cwd_path = Path.cwd() / rel
        if cwd_path.exists():
            return str(cwd_path)

        parent_path = Path(__file__).resolve().parent.parent / rel
        if parent_path.exists():
            return str(parent_path)

        if "assets/" in rel:
            assets_path = Path(__file__).resolve().parent / "assets" / rel.split("assets/")[-1]
        else:
            assets_path = Path(__file__).resolve().parent / rel
        if assets_path.exists():
            return str(assets_path)

    return str(abs_path)

PICS_DIR_INSTALL = Path(resource_path("pics"))

def ensure_dirs():
    try:
        PICS_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    try:
        if not DEFAULT_DB_PATH.exists():
            src_db = Path(resource_path("books_archive.db"))
            if src_db.exists():
                shutil.copyfile(src_db, DEFAULT_DB_PATH)
    except Exception:
        pass


def load_persian_font() -> Optional[str]:
    font_paths_to_try = [
        FONT_PATH,
        Path("assets/fonts/IRANSansX-Regular.ttf"),
        Path("fonts/IRANSansX-Regular.ttf"),
        Path("IRANSansX-Regular.ttf")
    ]

    for font_path in font_paths_to_try:
        try:
            fpath = Path(resource_path(str(font_path)))
            if not fpath.exists():
                fpath = Path(__file__).resolve().parent / font_path
                if not fpath.exists():
                    continue

            if fpath.exists():
                fid = QFontDatabase.addApplicationFont(str(fpath))
                fams = QFontDatabase.applicationFontFamilies(fid)
                if fams:
                    return fams[0]
        except Exception:
            continue

    return None


@lru_cache(maxsize=1000)
def get_id_cached(cur: sqlite3.Cursor, table: str, name: Optional[str]):
    if not name or (isinstance(name, float) and pd.isna(name)):
        return None

    cur.execute(f"SELECT id FROM {table} WHERE name=?", (name,))
    row = cur.fetchone()
    if row:
        return row[0]

    cur.execute(f"INSERT OR IGNORE INTO {table} (name) VALUES (?)", (name,))
    cur.execute(f"SELECT id FROM {table} WHERE name=?", (name,))
    row = cur.fetchone()
    return row[0] if row else None


def create_schema(conn: sqlite3.Connection, drop: bool = False):
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode = WAL")
    cur.execute("PRAGMA synchronous = NORMAL")
    cur.execute("PRAGMA cache_size = -2000")  # 2MB cache
    cur.execute("PRAGMA temp_store = MEMORY")
    if drop:
        tables = ['books', 'brands', 'models', 'machine_types', 'languages', 'meta']
        for table in tables:
            cur.execute(f"DROP TABLE IF EXISTS {table}")
            cur.execute(f"DROP INDEX IF EXISTS idx_{table}_name")
    cur.executescript(OPTIMIZED_SCHEMA)
    conn.commit()


def load_excel_to_df(xl_path: str) -> pd.DataFrame:
    try:
        df = pd.read_excel(xl_path, sheet_name=SHEET_NAME, engine='openpyxl')
        df = df.rename(columns=COLUMN_MAP)
        for col in ['brand', 'model', 'machine_type', 'title', 'language']:
            df[col] = df[col].astype('string')
            df[col] = df[col].str.strip()

        df['language'] = df['language'].fillna('Unknown')
        return df
    except Exception as e:
        raise Exception(f"خطا در بارگذاری اکسل: {e}")


def populate_replace(conn: sqlite3.Connection, df: pd.DataFrame):
    create_schema(conn, drop=True)
    cur = conn.cursor()
    conn.execute("BEGIN TRANSACTION")

    try:
        brands = df['brand'].dropna().unique()
        if len(brands) > 0:
            cur.executemany("INSERT OR IGNORE INTO brands (name) VALUES (?)",
                            [(str(b),) for b in brands])

        machine_types = df['machine_type'].dropna().unique()
        if len(machine_types) > 0:
            cur.executemany("INSERT OR IGNORE INTO machine_types (name) VALUES (?)",
                            [(str(m),) for m in machine_types])

        models = df['model'].dropna().unique()
        if len(models) > 0:
            cur.executemany("INSERT OR IGNORE INTO models (name) VALUES (?)",
                            [(str(m),) for m in models])

        languages = df['language'].dropna().unique()
        if len(languages) > 0:
            cur.executemany("INSERT OR IGNORE INTO languages (name) VALUES (?)",
                            [(str(l),) for l in languages])

        cur.execute("SELECT name, id FROM brands")
        brand_ids = {row[0]: row[1] for row in cur.fetchall()}

        cur.execute("SELECT name, id FROM machine_types")
        machine_type_ids = {row[0]: row[1] for row in cur.fetchall()}

        cur.execute("SELECT name, id FROM models")
        model_ids = {row[0]: row[1] for row in cur.fetchall()}

        cur.execute("SELECT name, id FROM languages")
        language_ids = {row[0]: row[1] for row in cur.fetchall()}

        books_data = []
        for _, r in df.iterrows():
            brand_id = brand_ids.get(str(r['brand'])) if pd.notna(r['brand']) else None
            mtype_id = machine_type_ids.get(str(r['machine_type'])) if pd.notna(r['machine_type']) else None
            model_id = model_ids.get(str(r['model'])) if pd.notna(r['model']) else None
            lang_id = language_ids.get(str(r['language'])) if pd.notna(r['language']) else None

            books_data.append((
                int(r['book_id']),
                str(r['title']),
                None if pd.isna(r.get('edition_year')) else str(r['edition_year']),
                None if pd.isna(r.get('location')) else str(r['location']),
                brand_id, model_id, mtype_id, lang_id
            ))

        cur.executemany('''
            INSERT OR REPLACE INTO books 
            (book_id, title, edition_year, location, brand_id, model_id, machine_type_id, language_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', books_data)

        conn.commit()
        print(f"✅ {len(books_data)} کتاب با موفقیت وارد دیتابیس شد")

    except Exception as e:
        conn.rollback()
        raise e


@lru_cache(maxsize=128)
def load_db_to_df(db_path: str) -> pd.DataFrame:
    conn = sqlite3.connect(db_path)
    try:
        query = '''
        SELECT 
            b.book_id AS "شماره",
            b.title AS "عنوان",
            COALESCE(br.name, '') AS "برند",
            COALESCE(m.name, '') AS "مدل",
            COALESCE(mt.name, '') AS "نوع ماشین‌آلات",
            COALESCE(lg.name, '') AS "زبان",
            COALESCE(b.edition_year, '') AS "سال/ورژن",
            COALESCE(b.location, '') AS "محل نگهداری"
        FROM books b
        LEFT JOIN brands br ON b.brand_id = br.id
        LEFT JOIN models m ON b.model_id = m.id
        LEFT JOIN machine_types mt ON b.machine_type_id = mt.id
        LEFT JOIN languages lg ON b.language_id = lg.id
        ORDER BY b.book_id
        '''

        dfb = pd.read_sql_query(query, conn)
        return dfb
    finally:
        conn.close()


def find_book_images_fast(book_id: str) -> List[str]:
    if book_id in BOOK_IMAGES_CACHE:
        return BOOK_IMAGES_CACHE[book_id]
    images: List[str] = []
    extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp'}
    search_dirs: List[Path] = []
    if PICS_DIR.exists():
        search_dirs.append(PICS_DIR)

    if 'PICS_DIR_INSTALL' in globals() and PICS_DIR_INSTALL.exists():
        if PICS_DIR_INSTALL not in search_dirs:
            search_dirs.append(PICS_DIR_INSTALL)

    if not search_dirs:
        BOOK_IMAGES_CACHE[book_id] = []
        return []

    try:
        for base_dir in search_dirs:
            for ext in extensions:
                img_path = base_dir / f"{book_id}{ext}"
                if img_path.exists():
                    images.append(str(img_path))

            for i in range(1, 10):
                for ext in extensions:
                    img_path = base_dir / f"{book_id}-{i}{ext}"
                    if img_path.exists():
                        images.append(str(img_path))

            for subdir in base_dir.iterdir():
                if subdir.is_dir():
                    for ext in extensions:
                        img_path = subdir / f"{book_id}{ext}"
                        if img_path.exists():
                            images.append(str(img_path))

                    for i in range(1, 10):
                        for ext in extensions:
                            img_path = subdir / f"{book_id}-{i}{ext}"
                            if img_path.exists():
                                images.append(str(img_path))

        images.sort()
        BOOK_IMAGES_CACHE[book_id] = images
        return images

    except Exception:
        BOOK_IMAGES_CACHE[book_id] = []
        return []

class LoadingOverlay(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LoadingOverlay")

        self.setStyleSheet("""
            #LoadingOverlay {
                background-color: rgba(255, 255, 255, 180);
                border-radius: 16px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        # اسپینر
        self.spinner = QLabel()
        self.spinner.setAlignment(Qt.AlignCenter)

        try:
            movie = QMovie(resource_path("assets/spinner.gif"))
            if movie.isValid():
                self.spinner.setMovie(movie)
                movie.start()
            else:
                self.spinner.setText("⏳")
                self.spinner.setStyleSheet("font-size: 32px; color: #3b82f6;")
        except:
            self.spinner.setText("⏳")
            self.spinner.setStyleSheet("font-size: 32px; color: #3b82f6;")

        self.label = QLabel("در حال بارگذاری...")
        self.label.setStyleSheet("""
            color: #475569;
            font-size: 14px;
            font-weight: bold;
            margin-top: 10px;
        """)

        layout.addWidget(self.spinner)
        layout.addWidget(self.label)

        self.hide()

    def set_message(self, message: str):
        self.label.setText(message)

    def show_overlay(self, message: str = "در حال بارگذاری..."):
        self.set_message(message)
        self.raise_()
        self.show()
        QApplication.processEvents()

    def hide_overlay(self):
        self.hide()


class WorkerSignals(QObject):
    started = Signal()
    finished = Signal(object)
    progress = Signal(int, str)
    error = Signal(str)


class DatabaseWorker(QRunnable):

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            self.signals.started.emit()
            result = self.func(*self.args, **self.kwargs)
            self.signals.finished.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))


class ImageViewerDialog(QDialog):
    def __init__(self, image_paths: List[str], start_index: int = 0, parent=None):
        super().__init__(parent)
        self.image_paths = image_paths
        self.current_index = start_index
        self.setWindowTitle("نمایش تصویر - آرشیو کتاب‌های کاوه")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(800, 600)
        self._setup_ui()
        self._load_image(self.current_index)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(30)
        shadow.setColor(QColor(0, 0, 0, 150))
        shadow.setOffset(0, 0)
        self.setGraphicsEffect(shadow)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)


        self.main_frame = QFrame()
        self.main_frame.setObjectName("ImageViewerFrame")
        self.main_frame.setStyleSheet("""
            #ImageViewerFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ffffff, stop:1 #f8fafc);
                border-radius: 16px;
                border: 1px solid #e2e8f0;
            }
        """)

        frame_layout = QVBoxLayout(self.main_frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)


        title_bar = QWidget()
        title_bar.setFixedHeight(60)
        title_bar_layout = QHBoxLayout(title_bar)
        title_bar_layout.setContentsMargins(20, 0, 20, 0)

        self.title_label = QLabel("نمایش تصویر")
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #1e293b;")

        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setFixedSize(32, 32)
        close_btn.setStyleSheet("""
            QToolButton {
                background: #fee2e2;
                color: #dc2626;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QToolButton:hover {
                background: #fecaca;
            }
        """)
        close_btn.clicked.connect(self.close)

        title_bar_layout.addWidget(self.title_label)
        title_bar_layout.addStretch()
        title_bar_layout.addWidget(close_btn)


        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(600, 400)
        self.image_label.setStyleSheet("""
            QLabel {
                background: #f8fafc;
                border-radius: 12px;
                border: 2px dashed #cbd5e1;
            }
        """)


        nav_widget = QWidget()
        nav_layout = QHBoxLayout(nav_widget)
        nav_layout.setContentsMargins(20, 10, 20, 10)

        self.prev_btn = QPushButton("◀ قبلی")
        self.next_btn = QPushButton("بعدی ▶")

        for btn in [self.prev_btn, self.next_btn]:
            btn.setFixedHeight(40)
            btn.setStyleSheet("""
                QPushButton {
                    background: #3b82f6;
                    color: white;
                    border-radius: 8px;
                    padding: 8px 16px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: #2563eb;
                }
                QPushButton:disabled {
                    background: #cbd5e1;
                    color: #64748b;
                }
            """)

        self.prev_btn.clicked.connect(self.show_previous)
        self.next_btn.clicked.connect(self.show_next)

        self.counter_label = QLabel("1 / 1")
        self.counter_label.setStyleSheet("color: #475569; font-weight: bold;")

        nav_layout.addWidget(self.prev_btn)
        nav_layout.addStretch()
        nav_layout.addWidget(self.counter_label)
        nav_layout.addStretch()
        nav_layout.addWidget(self.next_btn)


        frame_layout.addWidget(title_bar)
        frame_layout.addWidget(self.image_label, 1)
        frame_layout.addWidget(nav_widget)

        layout.addWidget(self.main_frame)


        self._update_navigation()

    def _load_image(self, index: int):
        if 0 <= index < len(self.image_paths):
            # بارگذاری تصویر در background thread
            QTimer.singleShot(0, lambda: self._load_image_async(index))

    def _load_image_async(self, index: int):
        pixmap = QPixmap(self.image_paths[index])
        if not pixmap.isNull():
            scaled = pixmap.scaled(self.image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.image_label.setPixmap(scaled)

            filename = Path(self.image_paths[index]).name
            self.title_label.setText(f"تصویر: {filename}")

            self.current_index = index
            self.counter_label.setText(f"{index + 1} / {len(self.image_paths)}")
            self._update_navigation()

    def _update_navigation(self):
        self.prev_btn.setEnabled(self.current_index > 0)
        self.next_btn.setEnabled(self.current_index < len(self.image_paths) - 1)

    def show_previous(self):
        if self.current_index > 0:
            self._load_image(self.current_index - 1)

    def show_next(self):
        if self.current_index < len(self.image_paths) - 1:
            self._load_image(self.current_index + 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.image_paths and hasattr(self, 'current_index'):
            self._load_image(self.current_index)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        elif event.key() == Qt.Key_Left:
            self.show_previous()
        elif event.key() == Qt.Key_Right:
            self.show_next()
        else:
            super().keyPressEvent(event)


class BookCard(QFrame):
    clicked = Signal(dict)

    def __init__(self, book_data: dict, images: List[str], parent=None):
        super().__init__(parent)
        self.book_data = book_data
        self.images = images
        self.current_image_index = 0
        self.is_loading = False

        self.setFixedSize(280, 320)
        self.setCursor(Qt.PointingHandCursor)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)

        self._setup_ui()
        self._load_first_image_async()

    def _setup_ui(self):
        self.setObjectName("BookCard")
        self.setStyleSheet("""
            #BookCard {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ffffff, stop:1 #f8fafc);
                border-radius: 16px;
                border: 1px solid #e2e8f0;
            }
            #BookCard:hover {
                border: 1px solid #3b82f6;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ffffff, stop:1 #eff6ff);
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.image_container = QFrame()
        self.image_container.setFixedHeight(160)
        self.image_container.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #f1f5f9, stop:1 #e2e8f0);
                border-radius: 12px;
                border: 1px solid #cbd5e1;
            }
        """)

        image_layout = QVBoxLayout(self.image_container)
        image_layout.setContentsMargins(0, 0, 0, 0)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("border: none;")

        self.pagination_widget = QWidget()
        self.pagination_widget.setFixedHeight(24)
        pagination_layout = QHBoxLayout(self.pagination_widget)
        pagination_layout.setContentsMargins(0, 0, 0, 0)
        pagination_layout.setSpacing(4)

        self.pagination_dots = []
        self.pagination_buttons = []

        if len(self.images) > 1:
            for i in range(min(len(self.images), 5)):
                btn = QToolButton()
                btn.setFixedSize(20, 20)
                btn.setText(str(i + 1))
                btn.setStyleSheet("""
                    QToolButton {
                        background: #cbd5e1;
                        color: #475569;
                        border-radius: 4px;
                        font-size: 9px;
                        font-weight: bold;
                    }
                    QToolButton:hover {
                        background: #94a3b8;
                    }
                    QToolButton:checked {
                        background: #3b82f6;
                        color: white;
                    }
                """)
                btn.setCheckable(True)
                btn.clicked.connect(lambda checked, idx=i: self._switch_image(idx))
                pagination_layout.addWidget(btn)
                self.pagination_buttons.append(btn)

            if self.pagination_buttons:
                self.pagination_buttons[0].setChecked(True)

        pagination_layout.addStretch()

        image_layout.addWidget(self.image_label, 1)
        image_layout.addWidget(self.pagination_widget)

        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setSpacing(4)

        book_no = QLabel(f"📘 شماره: {self.book_data.get('شماره', '')}")
        book_no.setStyleSheet("font-weight: bold; color: #1e40af;")

        title_text = self.book_data.get('عنوان', 'بدون عنوان')
        title = QLabel(title_text)
        title.setWordWrap(True)
        title.setMaximumHeight(40)
        title.setStyleSheet("""
            font-weight: bold;
            color: #1e293b;
            font-size: 13px;
        """)

        brand_model = QLabel(f"🏭 {self.book_data.get('برند', '')} | {self.book_data.get('مدل', '')}")
        brand_model.setStyleSheet("color: #475569; font-size: 11px;")

        type_lang = QLabel(f"🔧 {self.book_data.get('نوع ماشین‌آلات', '')} | {self.book_data.get('زبان', '')}")
        type_lang.setStyleSheet("color: #64748b; font-size: 11px;")

        info_layout.addWidget(book_no)
        info_layout.addWidget(title)
        info_layout.addWidget(brand_model)
        info_layout.addWidget(type_lang)

        layout.addWidget(self.image_container)
        layout.addWidget(info_widget)

    def _load_first_image_async(self):
        if self.images:
            QTimer.singleShot(50, self._load_image)
        else:
            self._create_placeholder_image()

    def _load_image(self, index: int = 0):
        if index < 0 or index >= len(self.images):
            return

        self.current_image_index = index

        for i, btn in enumerate(self.pagination_buttons):
            btn.setChecked(i == index)

        thumbnail = image_cache.get_thumbnail(self.images[index])
        if thumbnail:
            self.image_label.setPixmap(thumbnail)
        else:
            self._create_placeholder_image()

    def _switch_image(self, index: int):
        if index != self.current_image_index:
            self._load_image(index)

    def _create_placeholder_image(self):
        pixmap = QPixmap(240, 140)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        gradient = QLinearGradient(0, 0, 0, 140)
        gradient.setColorAt(0, QColor(241, 245, 249))
        gradient.setColorAt(1, QColor(226, 232, 240))
        painter.setBrush(QBrush(gradient))
        painter.setPen(QPen(QColor(203, 213, 225), 1))
        painter.drawRoundedRect(0, 0, 240, 140, 8, 8)

        painter.setPen(QPen(QColor(100, 116, 139), 2))
        painter.drawEllipse(100, 30, 40, 40)
        painter.drawText(QRect(100, 30, 40, 40), Qt.AlignCenter, "📚")

        title = self.book_data.get('عنوان', 'بدون تصویر')
        if len(title) > 25:
            title = title[:25] + "..."

        painter.setPen(QPen(QColor(71, 85, 105)))
        painter.setFont(QFont("Arial", 9))
        painter.drawText(QRect(20, 90, 200, 40), Qt.AlignCenter | Qt.TextWordWrap, title)

        painter.end()
        self.image_label.setPixmap(pixmap)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.book_data)
            super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and self.images:
            dialog = ImageViewerDialog(self.images, self.current_image_index, self)
            dialog.exec()
        super().mouseDoubleClickEvent(event)

    def enterEvent(self, event):
        self.setStyleSheet("""
            #BookCard {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ffffff, stop:1 #eff6ff);
                border-radius: 16px;
                border: 1px solid #3b82f6;
            }
        """)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setStyleSheet("""
            #BookCard {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ffffff, stop:1 #f8fafc);
                border-radius: 16px;
                border: 1px solid #e2e8f0;
            }
        """)
        super().leaveEvent(event)


class GalleryView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.books_data = []
        self.current_filtered_data = []
        self.is_loading = False
        self.thread_pool = QThreadPool.globalInstance()
        self.thread_pool.setMaxThreadCount(4)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # Loading overlay
        self.loading_overlay = LoadingOverlay(self)
        self.loading_overlay.setFixedSize(self.size())

        # Scroll area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                background: #f1f5f9;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #cbd5e1;
                border-radius: 5px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: #94a3b8;
            }
        """)

        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")

        self.grid_layout = QGridLayout(self.container)
        self.grid_layout.setSpacing(20)
        self.grid_layout.setAlignment(Qt.AlignTop)

        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)

        self.empty_state = QWidget()
        empty_layout = QVBoxLayout(self.empty_state)
        empty_layout.setAlignment(Qt.AlignCenter)

        empty_icon = QLabel("📚")
        empty_icon.setStyleSheet("font-size: 64px;")
        empty_icon.setAlignment(Qt.AlignCenter)

        empty_text = QLabel("کتابی یافت نشد")
        empty_text.setStyleSheet("font-size: 18px; color: #64748b; margin-top: 20px;")
        empty_text.setAlignment(Qt.AlignCenter)

        empty_layout.addWidget(empty_icon)
        empty_layout.addWidget(empty_text)

        layout.addWidget(self.empty_state)
        self.empty_state.hide()

        layout.addWidget(self.loading_overlay)

    def show_loading(self, message: str = "در حال بارگذاری تصاویر..."):
        self.loading_overlay.set_message(message)
        self.loading_overlay.show_overlay()
        self.is_loading = True

    def hide_loading(self):
        self.loading_overlay.hide_overlay()
        self.is_loading = False

    def set_books_data(self, books_data: List[dict]):
        self.books_data = books_data
        self.show_loading("در حال آماده‌سازی نمایش...")
        QTimer.singleShot(50, lambda: self.display_books_async(books_data))

    def display_books_async(self, books_data: List[dict]):
        self.current_filtered_data = books_data

        for i in reversed(range(self.grid_layout.count())):
            widget = self.grid_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()

        if not books_data:
            self.empty_state.show()
            self.hide_loading()
            return

        self.empty_state.hide()

        cols = max(3, min(5, self.width() // 300))

        self._create_cards_gradually(books_data, cols, 0)

    def _create_cards_gradually(self, books_data: List[dict], cols: int, index: int, batch_size: int = 10):
        if index >= len(books_data):
            self.hide_loading()
            return

        end_index = min(index + batch_size, len(books_data))

        for i in range(index, end_index):
            book = books_data[i]
            book_id = str(book.get('شماره', ''))

            images = find_book_images_fast(book_id)

            card = BookCard(book, images, self.container)
            card.clicked.connect(self._on_card_clicked)

            row = i // cols
            col = i % cols
            self.grid_layout.addWidget(card, row, col)

        QTimer.singleShot(10, lambda: self._create_cards_gradually(books_data, cols, end_index, batch_size))

    def _on_card_clicked(self, book_data: dict):
        pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.loading_overlay.setFixedSize(self.size())
        if self.current_filtered_data and not self.is_loading:
            QTimer.singleShot(100, lambda: self.display_books_async(self.current_filtered_data))


class ViewToggleWidget(QWidget):
    view_changed = Signal(str)  # 'table' or 'gallery'

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.table_btn = QToolButton()
        self.gallery_btn = QToolButton()

        self.table_btn.setIcon(QIcon.fromTheme("view-list-details"))
        self.table_btn.setText("نمایش لیستی")
        self.table_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.table_btn.setCheckable(True)
        self.table_btn.setChecked(True)

        self.gallery_btn.setIcon(QIcon.fromTheme("view-grid"))
        self.gallery_btn.setText("نمایش تصویری")
        self.gallery_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.gallery_btn.setCheckable(True)

        for btn in [self.table_btn, self.gallery_btn]:
            btn.setFixedSize(140, 40)
            btn.setStyleSheet("""
                QToolButton {
                    background: #f1f5f9;
                    border: 1px solid #cbd5e1;
                    border-radius: 8px;
                    padding: 8px 12px;
                    color: #475569;
                    font-weight: bold;
                }
                QToolButton:checked {
                    background: #3b82f6;
                    color: white;
                    border-color: #3b82f6;
                }
                QToolButton:hover:not(:checked) {
                    background: #e2e8f0;
                }
            """)

        self.table_btn.clicked.connect(lambda: self._toggle_view('table'))
        self.gallery_btn.clicked.connect(lambda: self._toggle_view('gallery'))

        layout.addStretch()
        layout.addWidget(self.table_btn)
        layout.addWidget(self.gallery_btn)

    def _toggle_view(self, view_type: str):
        if view_type == 'table':
            self.table_btn.setChecked(True)
            self.gallery_btn.setChecked(False)
        else:
            self.table_btn.setChecked(False)
            self.gallery_btn.setChecked(True)

        self.view_changed.emit(view_type)


class ImageButtonDelegate(QStyledItemDelegate):
    clicked = Signal(QModelIndex)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.button_rect = QRect()

    def paint(self, painter, option: QStyleOptionViewItem, index: QModelIndex):
        if index.column() == 0:
            btn_rect = option.rect.adjusted(10, 5, -10, -5)
            self.button_rect = btn_rect
            painter.save()

            if option.state & QStyle.State_MouseOver:
                painter.setBrush(QColor(59, 130, 246))
                painter.setPen(QColor(37, 99, 235))
            else:
                painter.setBrush(QColor(37, 99, 235))
                painter.setPen(QColor(30, 64, 175))

            painter.drawRoundedRect(btn_rect, 6, 6)

            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QFont("Arial", 9, QFont.Bold))

            book_id = index.sibling(index.row(), 1).data()
            if book_id:
                images = find_book_images_fast(str(book_id))
                btn_text = f"تصاویر ({len(images)})" if images else "بدون تصویر"
            else:
                btn_text = "نمایش تصویر"

            painter.drawText(btn_rect, Qt.AlignCenter, btn_text)

            painter.restore()
        else:
            super().paint(painter, option, index)

    def editorEvent(self, event, model, option, index):
        if index.column() == 0 and event.type() == QMouseEvent.MouseButtonRelease:
            # استفاده از position().toPoint() به جای pos() برای Qt6
            pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
            if self.button_rect.contains(pos):
                self.clicked.emit(index)
                return True
        return False


class DataFrameModel(QAbstractTableModel):

    def __init__(self, df: pd.DataFrame):
        super().__init__()
        self._df = df.copy()
        self._data_cache = {}

    def set_dataframe(self, df: pd.DataFrame):
        self.beginResetModel()
        self._df = df.copy()
        self._data_cache.clear()
        self.endResetModel()

    def dataframe(self) -> pd.DataFrame:
        return self._df

    def get_book_data(self, index: int) -> dict:
        if 0 <= index < len(self._df):
            return self._df.iloc[index].to_dict()
        return {}

    def get_all_book_data(self) -> List[dict]:
        return self._df.to_dict('records')

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._df)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(DISPLAY_COLUMNS)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        row = index.row()
        col = index.column()

        if col == 0:
            if role == Qt.DisplayRole:
                return ""
            elif role == Qt.TextAlignmentRole:
                return int(Qt.AlignCenter)
            return None

        cache_key = (row, col - 1, role)
        if cache_key in self._data_cache:
            return self._data_cache[cache_key]

        if row >= len(self._df):
            return None

        df_col = col - 1

        if df_col < len(self._df.columns):
            val = self._df.iat[row, df_col]

            if role in (Qt.DisplayRole, Qt.EditRole):
                result = "" if pd.isna(val) else str(val)
            elif role == Qt.TextAlignmentRole:
                result = int(Qt.AlignCenter)
            elif role == Qt.ToolTipRole:
                s = "" if pd.isna(val) else str(val)
                result = s if len(s) > 40 else None
            else:
                result = None

            if result is not None:
                self._data_cache[cache_key] = result

            return result

        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            if section < len(DISPLAY_COLUMNS):
                return DISPLAY_COLUMNS[section]
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemIsEnabled
        if index.column() == 0:
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable


class WordWrapDelegate(QStyledItemDelegate):

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

            width = max(option.rect.width(), 360)
            doc = QTextDocument()
            doc.setDefaultFont(opt.font)
            doc.setTextWidth(width)
            doc.setPlainText(text)
            h = int(doc.size().height()) + 12
            return QSize(int(doc.idealWidth()), h)
        return super().sizeHint(option, index)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1400, 800)
        self.setMinimumSize(1024, 600)

        self.settings = QSettings(ORG_NAME, APP_KEY)
        self._db_path = DEFAULT_DB
        self._df_full = pd.DataFrame(columns=[col for col in DISPLAY_COLUMNS if col != "تصویر"])
        self._wrap_enabled = True
        self._current_view = 'table'
        self._filter_timer = QTimer()
        self._filter_timer.setSingleShot(True)
        self._filter_timer.timeout.connect(self.apply_filters_delayed)
        self._is_filtering = False

        self.thread_pool = QThreadPool.globalInstance()
        self.thread_pool.setMaxThreadCount(2)

        QApplication.instance().setLayoutDirection(Qt.RightToLeft)
        fam = load_persian_font()
        base_font = QFont(fam if fam else QApplication.font().family(), 10)
        QApplication.instance().setFont(base_font)

        self.setStyleSheet(self._app_stylesheet())

        self._build_ui()
        self._load_db_if_exists()
        self._update_filters()

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("آماده")

        self._build_menu()
        self._restore_window_state()

    def _build_ui(self):
        self.view_toggle = ViewToggleWidget()
        self.view_toggle.view_changed.connect(self._switch_view)

        banner = self._banner_widget()
        filters = self._filters_panel()

        self.table = QTableView()
        self.table.setObjectName("BooksTable")
        self.model = DataFrameModel(self._df_full)
        self.table.setModel(self.model)

        self.table.verticalHeader().setVisible(False)

        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.Interactive)
        h.setStretchLastSection(False)
        h.setSectionsClickable(True)

        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(True)
        self.table.setTextElideMode(Qt.ElideNone)
        self.table.setSortingEnabled(True)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        self.table.verticalHeader().setDefaultSectionSize(60)

        self._apply_wrap_delegate()

        self.image_delegate = ImageButtonDelegate(self.table)
        self.table.setItemDelegateForColumn(0, self.image_delegate)  # ستون اول
        self.image_delegate.clicked.connect(self._show_book_images)

        self.gallery_view = GalleryView()

        self.stacked_widget = QStackedWidget()
        self.stacked_widget.addWidget(self.table)
        self.stacked_widget.addWidget(self.gallery_view)

        right = QWidget()
        right_l = QVBoxLayout(right)
        right_l.setSpacing(10)
        right_l.addWidget(banner)
        right_l.addWidget(self.view_toggle)
        right_l.addWidget(self.stacked_widget)

        split = QSplitter()
        split.addWidget(filters)
        split.addWidget(right)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([300, 1100])

        cw = QWidget()
        cwl = QVBoxLayout(cw)
        cwl.addWidget(split)
        self.setCentralWidget(cw)

    def _banner_widget(self) -> QWidget:
        w = QWidget()
        l = QHBoxLayout(w)
        l.setContentsMargins(12, 12, 12, 12)

        logo_lbl = QLabel()
        logo_locations = [
            LOGO_PATH,
            Path("assets/logo.jpg"),
            Path("logo.jpg"),
            Path("assets/logo.png"),
            Path("logo.png")
        ]

        logo_found = False
        for logo_loc in logo_locations:
            try:
                logo_path = Path(resource_path(str(logo_loc)))
                if logo_path.exists():
                    pixmap = QPixmap(str(logo_path))
                    if not pixmap.isNull():
                        scaled_pixmap = pixmap.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        logo_lbl.setPixmap(scaled_pixmap)
                        logo_found = True
                        break
            except Exception:
                continue

        if not logo_found:
            placeholder = QPixmap(48, 48)
            placeholder.fill(QColor("#3b82f6"))
            painter = QPainter(placeholder)
            painter.setPen(QColor("white"))
            painter.setFont(QFont("Arial", 16, QFont.Bold))
            painter.drawText(placeholder.rect(), Qt.AlignCenter, "📘")
            painter.end()
            logo_lbl.setPixmap(placeholder)

        title = QLabel("📘 آرشیو کتاب‌های فنی شرکت خدمات دریایی و بندری کاوه")
        title.setObjectName("HeaderTitle")

        self.count_lbl = QLabel("تعداد نتایج: 0")
        self.count_lbl.setObjectName("CountLabel")

        l.addWidget(logo_lbl)
        l.addWidget(title)
        l.addStretch(1)
        l.addWidget(self.count_lbl)

        return w

    def _filters_panel(self) -> QWidget:
        g = QGroupBox("مرور و فیلتر")
        g.setObjectName("Card")
        lay = QVBoxLayout(g)

        self.brand_cmb = QComboBox()
        self.type_cmb = QComboBox()
        self.model_cmb = QComboBox()
        self.lang_cmb = QComboBox()

        for cmb in (self.brand_cmb, self.type_cmb, self.model_cmb, self.lang_cmb):
            cmb.setEditable(False)
            cmb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        search_widget = QWidget()
        search_layout = QHBoxLayout(search_widget)
        search_layout.setContentsMargins(0, 0, 0, 0)

        self.search_edt = QLineEdit()
        self.search_edt.setPlaceholderText("جستجو در عنوان...")
        self.search_btn = QPushButton("🔍")
        self.search_btn.setFixedWidth(50)
        self.search_btn.setToolTip("جستجو")

        search_layout.addWidget(self.search_edt)
        search_layout.addWidget(self.search_btn)

        btn_apply = QPushButton("اعمال فیلترها")
        btn_clear = QPushButton("پاک‌سازی فیلترها")

        lay.addWidget(QLabel("برند:"))
        lay.addWidget(self.brand_cmb)
        lay.addSpacing(5)

        lay.addWidget(QLabel("نوع ماشین‌آلات:"))
        lay.addWidget(self.type_cmb)
        lay.addSpacing(5)

        lay.addWidget(QLabel("مدل:"))
        lay.addWidget(self.model_cmb)
        lay.addSpacing(5)

        lay.addWidget(QLabel("زبان:"))
        lay.addWidget(self.lang_cmb)
        lay.addSpacing(10)

        lay.addWidget(QLabel("جستجو در عنوان:"))
        lay.addWidget(search_widget)

        lay.addSpacing(15)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(btn_apply)
        btn_layout.addWidget(btn_clear)
        lay.addLayout(btn_layout)

        lay.addStretch(1)

        self.search_btn.clicked.connect(self.apply_filters)
        btn_apply.clicked.connect(self.apply_filters)
        btn_clear.clicked.connect(self.clear_filters)

        self.search_edt.textChanged.connect(self._on_search_text_changed)
        return g

    def _on_search_text_changed(self):
        if not self._is_filtering:
            self._filter_timer.start(300)  # تاخیر 300 میلی‌ثانیه

    def apply_filters_delayed(self):
        self.apply_filters()

    def _switch_view(self, view_type: str):
        if self._is_filtering:
            return

        self._current_view = view_type
        if view_type == 'table':
            self.view_toggle.table_btn.setChecked(True)
            self.view_toggle.gallery_btn.setChecked(False)
            self.stacked_widget.setCurrentWidget(self.table)
            self.smart_autofit_columns()
        else:
            self.view_toggle.table_btn.setChecked(False)
            self.view_toggle.gallery_btn.setChecked(True)
            self.stacked_widget.setCurrentWidget(self.gallery_view)
            self.gallery_view.show_loading("در حال بارگذاری نمایش تصویری...")
            QTimer.singleShot(50, self._update_gallery_view_delayed)

    def _update_gallery_view_delayed(self):
        df_filtered = self.model.dataframe()
        books_data = df_filtered.to_dict('records') if not df_filtered.empty else []
        self.gallery_view.set_books_data(books_data)

    def _load_db_if_exists(self):
        if Path(self._db_path).exists():
            try:
                self.statusBar().showMessage("در حال بارگذاری دیتابیس...")
                QApplication.processEvents()

                self._df_full = load_db_to_df(self._db_path)
                self.model.set_dataframe(self._df_full)

                self.statusBar().showMessage(f"دیتابیس خوانده شد: {len(self._df_full)} کتاب")
                self._update_filters()
                self.apply_filters()

            except Exception as e:
                QMessageBox.critical(self, APP_NAME, f"خطا در خواندن دیتابیس:\n{str(e)}")
                self.statusBar().showMessage("خطا در بارگذاری دیتابیس")
        else:
            self.statusBar().showMessage("دیتابیس پیدا نشد. از منوی فایل → بازسازی از اکسل استفاده کنید.")

    def _update_filters(self):
        df = self._df_full

        if df.empty:
            for cmb in (self.brand_cmb, self.type_cmb, self.model_cmb, self.lang_cmb):
                self._fill_combo(cmb, ["(همه)"])
            return

        def get_sorted_options(series):
            values = series.dropna().unique()
            values_list = list(values)
            values_list.sort(key=lambda x: str(x).strip())
            return values_list

        try:
            self._fill_combo(self.brand_cmb, ["(همه)"] + get_sorted_options(df["برند"]))
            self._fill_combo(self.type_cmb, ["(همه)"] + get_sorted_options(df["نوع ماشین‌آلات"]))
            self._fill_combo(self.model_cmb, ["(همه)"] + get_sorted_options(df["مدل"]))
            self._fill_combo(self.lang_cmb, ["(همه)"] + get_sorted_options(df["زبان"]))
        except Exception as e:
            print(f"خطا در بروزرسانی فیلترها: {e}")

    @staticmethod
    def _fill_combo(cmb: QComboBox, items):
        cmb.blockSignals(True)
        cmb.clear()
        cmb.addItems(items)
        if cmb.count() > 0:
            cmb.setCurrentIndex(0)
        cmb.blockSignals(False)

    def clear_filters(self):
        for cmb in (self.brand_cmb, self.type_cmb, self.model_cmb, self.lang_cmb):
            cmb.setCurrentIndex(0)
        self.search_edt.clear()
        self.apply_filters()

    def apply_filters(self):
        if self._df_full.empty:
            return

        self._is_filtering = True
        self.statusBar().showMessage("در حال اعمال فیلترها...")
        QTimer.singleShot(10, self._apply_filters_async)

    def _apply_filters_async(self):
        try:
            df = self._df_full.copy()
            mask = np.ones(len(df), dtype=bool)
            f_brand = self.brand_cmb.currentText()
            if f_brand and f_brand != "(همه)":
                mask &= (df["برند"].values == f_brand)

            f_type = self.type_cmb.currentText()
            if f_type and f_type != "(همه)":
                mask &= (df["نوع ماشین‌آلات"].values == f_type)

            f_model = self.model_cmb.currentText()
            if f_model and f_model != "(همه)":
                mask &= (df["مدل"].values == f_model)

            f_lang = self.lang_cmb.currentText()
            if f_lang and f_lang != "(همه)":
                mask &= (df["زبان"].values == f_lang)

            q = self.search_edt.text().strip()
            if q:
                search_mask = df["عنوان"].astype(str).str.contains(q, case=False, na=False)
                mask &= search_mask.values

            filtered_df = df[mask]

            self.model.set_dataframe(filtered_df)
            count = len(filtered_df)
            self.count_lbl.setText(f"تعداد نتایج: {count}")

            if self._current_view == 'gallery':
                books_data = filtered_df.to_dict('records') if count > 0 else []
                self.gallery_view.set_books_data(books_data)

            if self._current_view == 'table':
                self.smart_autofit_columns()

            self.statusBar().showMessage(f"اعمال فیلترها تکمیل شد ({count} مورد)")

        except Exception as e:
            self.statusBar().showMessage(f"خطا در اعمال فیلترها: {e}")
        finally:
            self._is_filtering = False

    def action_rebuild_from_excel(self):
        xlsx, _ = QFileDialog.getOpenFileName(
            self,
            "انتخاب فایل اکسل",
            "",
            "فایل‌های اکسل (*.xlsx *.xls)"
        )

        if not xlsx:
            return

        progress = QProgressDialog("در حال بازسازی دیتابیس...", "لغو", 0, 100, self)
        progress.setWindowTitle("بازسازی از اکسل")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(10)
        QApplication.processEvents()

        try:
            progress.setValue(20)
            QApplication.processEvents()
            df = load_excel_to_df(xlsx)

            progress.setValue(40)
            QApplication.processEvents()

            conn = sqlite3.connect(self._db_path)

            progress.setValue(60)
            QApplication.processEvents()

            populate_replace(conn, df)
            conn.close()

            progress.setValue(80)
            QApplication.processEvents()

            self._df_full = load_db_to_df(self._db_path)
            self.model.set_dataframe(self._df_full)

            progress.setValue(90)
            QApplication.processEvents()

            self._update_filters()
            self.apply_filters()

            progress.setValue(100)

            QMessageBox.information(self, APP_NAME,
                                    f"✅ دیتابیس با موفقیت بازسازی شد.\n{len(df)} کتاب وارد شد.")

        except Exception as e:
            progress.close()
            QMessageBox.critical(self, APP_NAME, f"خطا در تبدیل اکسل به دیتابیس:\n{str(e)}")

    def action_export_csv(self):
        if self.model.dataframe().empty:
            QMessageBox.information(self, APP_NAME, "جدولی برای خروجی وجود ندارد.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "ذخیره به عنوان CSV",
            f"نتایج_کتاب‌ها_{time.strftime('%Y%m%d_%H%M%S')}.csv",
            "فایل CSV (*.csv)"
        )

        if not path:
            return

        try:
            self.model.dataframe().to_csv(path, index=False, encoding='utf-8-sig')
            QMessageBox.information(self, APP_NAME, f"فایل CSV با موفقیت ذخیره شد:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, f"خطا در ذخیره فایل:\n{str(e)}")

    def action_choose_db(self):
        db, _ = QFileDialog.getOpenFileName(
            self,
            "انتخاب فایل دیتابیس",
            "",
            "فایل‌های دیتابیس SQLite (*.db *.sqlite *.sqlite3)"
        )

        if not db:
            return

        self._db_path = db
        self._load_db_if_exists()

    def _show_book_images(self, index: QModelIndex):
        if index.row() < 0 or index.row() >= len(self.model.dataframe()):
            return

        book_data = self.model.get_book_data(index.row())
        book_id = str(book_data.get('شماره', ''))

        if not book_id:
            return

        images = find_book_images_fast(book_id)

        if not images:
            QMessageBox.information(self, APP_NAME,
                                    f"برای کتاب شماره {book_id} تصویری یافت نشد.")
            return

        dialog = ImageViewerDialog(images, 0, self)
        dialog.exec()

    def _build_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("فایل")
        act_open_excel = QAction("بازسازی از اکسل...", self)
        act_open_excel.setShortcut(QKeySequence("Ctrl+O"))
        act_open_excel.triggered.connect(self.action_rebuild_from_excel)
        file_menu.addAction(act_open_excel)
        act_export_csv = QAction("خروجی CSV از نتایج", self)
        act_export_csv.setShortcut(QKeySequence("Ctrl+S"))
        act_export_csv.triggered.connect(self.action_export_csv)
        file_menu.addAction(act_export_csv)
        file_menu.addSeparator()
        act_choose_db = QAction("انتخاب دیتابیس...", self)
        act_choose_db.triggered.connect(self.action_choose_db)
        file_menu.addAction(act_choose_db)
        file_menu.addSeparator()
        act_exit = QAction("خروج", self)
        act_exit.setShortcut(QKeySequence("Ctrl+Q"))
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)
        view_menu = menubar.addMenu("نمایش")
        self.act_wrap = QAction("نمایش عناوین چندخطی", self)
        self.act_wrap.setCheckable(True)
        self.act_wrap.setChecked(self._wrap_enabled)
        self.act_wrap.triggered.connect(self.toggle_wrap)
        view_menu.addAction(self.act_wrap)
        act_fit = QAction("متناسب‌سازی ستون‌ها", self)
        act_fit.setShortcut(QKeySequence("Ctrl+F"))
        act_fit.triggered.connect(self.smart_autofit_columns)
        view_menu.addAction(act_fit)
        act_reset = QAction("بازنشانی اندازه ستون‌ها", self)
        act_reset.triggered.connect(self.reset_columns_default)
        view_menu.addAction(act_reset)
        view_menu.addSeparator()
        act_table = QAction("نمایش لیستی", self)
        act_table.setCheckable(True)
        act_table.setChecked(self._current_view == 'table')
        act_table.triggered.connect(lambda: self._switch_view('table'))
        view_menu.addAction(act_table)
        act_gallery = QAction("نمایش تصویری", self)
        act_gallery.setCheckable(True)
        act_gallery.setChecked(self._current_view == 'gallery')
        act_gallery.triggered.connect(lambda: self._switch_view('gallery'))
        view_menu.addAction(act_gallery)
        help_menu = menubar.addMenu("کمک")
        act_about = QAction("درباره برنامه", self)
        act_about.triggered.connect(self.show_about)
        help_menu.addAction(act_about)

    def show_about(self):
        about_text = f"""
        <h2>{APP_NAME}</h2>
        <p>نسخه: 2.0</p>
        <p>توسعه‌دهنده: امیر فرشادفر - شرکت خدمات دریایی و بندری کاوه</p>
        <p>توضیحات: برنامه مدیریت آرشیو کتاب‌های فنی و منوال‌های دستگاه‌ها</p>
        <p>ویژگی‌ها:</p>
        <ul>
            <li>مدیریت آرشیو کتاب‌های فنی</li>
            <li>پشتیبانی از نمایش لیستی و تصویری</li>
            <li>جستجو و فیلتر پیشرفته</li>
            <li>پشتیبانی از تصاویر کتاب‌ها</li>
            <li>سرعت بالا و بهینه‌سازی شده</li>
        </ul>
        """

        QMessageBox.about(self, "درباره برنامه", about_text)

    def toggle_wrap(self, checked: bool):
        self._wrap_enabled = checked
        self._apply_wrap_delegate()
        self.smart_autofit_columns()

    def _apply_wrap_delegate(self):
        title_idx = 2
        if self._wrap_enabled:
            self.table.setItemDelegateForColumn(title_idx, WordWrapDelegate({title_idx}, self.table))
        else:
            self.table.setItemDelegateForColumn(title_idx, QStyledItemDelegate(self.table))

    def smart_autofit_columns(self):
        df = self.model.dataframe()
        if df is None or df.empty:
            return

        self.table.setUpdatesEnabled(False)
        fm = self.table.fontMetrics()
        h = self.table.horizontalHeader()

        padding = 24

        for col in range(len(DISPLAY_COLUMNS)):
            if col == 0:
                h.resizeSection(col, 120)
                continue

            header_text = DISPLAY_COLUMNS[col]
            maxw = fm.horizontalAdvance(header_text) + padding

            df_col = col - 1
            if df_col < df.shape[1]:
                series = df.iloc[:100, df_col].astype(str)
                for val in series:
                    maxw = max(maxw, fm.horizontalAdvance(val) + padding)

            name = DISPLAY_COLUMNS[col]
            if name == "عنوان":
                minw, max_allowed = 300, 800
            elif name in ("محل نگهداری", "برند", "نوع ماشین‌آلات"):
                minw, max_allowed = 150, 400
            elif name == "شماره":
                minw, max_allowed = 80, 120
            else:
                minw, max_allowed = 100, 300

            width = max(minw, min(maxw, max_allowed))
            h.resizeSection(col, int(width))

        self.table.resizeRowsToContents()
        self.table.setUpdatesEnabled(True)

        self._save_header_state()

    def reset_columns_default(self):
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.Interactive)
        self.smart_autofit_columns()

    def closeEvent(self, event):
        self._save_window_state()
        super().closeEvent(event)

    def _save_window_state(self):
        self.settings.beginGroup("window")
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("state", self.saveState())
        self.settings.endGroup()
        self._save_header_state()

    def _restore_window_state(self):
        self.settings.beginGroup("window")
        geo = self.settings.value("geometry")
        state = self.settings.value("state")

        if geo is not None:
            self.restoreGeometry(geo)
        if state is not None:
            self.restoreState(state)

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

    @staticmethod
    def _app_stylesheet() -> str:
        return """
        QMainWindow, QWidget {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #f8fafc, stop:1 #ffffff);
            color: #0f172a;
        }

        QGroupBox#Card {
            background: white;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 16px;
            margin-top: 12px;
        }

        QGroupBox::title {
            subcontrol-origin: margin;
            right: 12px;
            padding: 0 8px;
            color: #3b82f6;
            font-weight: bold;
            font-size: 14px;
        }

        QLabel#HeaderTitle {
            font-weight: 700;
            font-size: 18px;
            color: #1e293b;
        }

        QLabel#CountLabel {
            color: #475569;
            font-weight: bold;
            background: #f1f5f9;
            padding: 10px 20px;
            border-radius: 10px;
            border: 1px solid #e2e8f0;
        }

        QLineEdit {
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 10px 12px;
            background: white;
            font-size: 13px;
        }

        QLineEdit:focus {
            border: 2px solid #3b82f6;
            outline: none;
        }

        QComboBox {
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 10px 12px;
            background: white;
            font-size: 13px;
            min-height: 20px;
        }

        QComboBox::drop-down {
            border: none;
            width: 30px;
        }

        QComboBox::down-arrow {
            image: none;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 5px solid #64748b;
            width: 0;
            height: 0;
            margin-right: 10px;
        }

        QComboBox QAbstractItemView {
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            background: white;
            selection-background-color: #3b82f6;
            selection-color: white;
        }

        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #3b82f6, stop:1 #2563eb);
            color: white;
            border: none;
            border-radius: 8px;
            padding: 12px 20px;
            font-weight: bold;
            font-size: 13px;
        }

        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #2563eb, stop:1 #1d4ed8);
        }

        QPushButton:pressed {
            background: #1e40af;
        }

        QPushButton:disabled {
            background: #cbd5e1;
            color: #64748b;
        }

        QTableView#BooksTable {
            background: white;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            alternate-background-color: #f8fafc;
            gridline-color: #e2e8f0;
            selection-background-color: #dbeafe;
            selection-color: #1e40af;
        }

        QTableView#BooksTable::item {
            padding: 8px;
        }

        QHeaderView::section {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #f1f5f9, stop:1 #e2e8f0);
            padding: 12px 8px;
            border: none;
            border-right: 1px solid #e2e8f0;
            font-weight: bold;
            color: #475569;
            font-size: 13px;
        }

        QStatusBar {
            background: #f8fafc;
            border-top: 1px solid #e2e8f0;
            color: #64748b;
            font-size: 12px;
        }

        QStatusBar::item {
            border: none;
        }

        QToolButton {
            background: transparent;
            border: none;
            padding: 6px;
            border-radius: 6px;
        }

        QToolButton:hover {
            background: #f1f5f9;
        }

        QToolButton:pressed {
            background: #e2e8f0;
        }

        #LoadingOverlay {
            background-color: rgba(255, 255, 255, 0.9);
            border-radius: 16px;
        }
        """


def main():
    ensure_dirs()
    app = QApplication(sys.argv)
    app.setOrganizationName(ORG_NAME)
    app.setApplicationName(APP_KEY)
    app.setStyle(QStyleFactory.create("Fusion"))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()