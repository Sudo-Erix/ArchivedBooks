#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
اسکریپت ساخت Installer برای برنامه آرشیو کتاب‌های فنی کاوه
توسعه‌دهنده: امیر فرشادفر - کارشناس مکانیک
شرکت خدمات دریایی و بندری کاوه
"""

import os
import sys
import shutil
import time
import subprocess
from pathlib import Path
import hashlib

# ==================== تنظیمات پروژه ====================
PROJECT_NAME = "آرشیو کتاب‌های فنی کاوه"
PROJECT_VERSION = "2.0.0"
COMPANY_NAME = "شرکت خدمات دریایی و بندری کاوه"
DEVELOPER = "امیر فرشادفر (کارشناس مکانیک)"
APP_NAME = "KavehBooks"
APP_KEY = "KavehBooks_v2"
COPYRIGHT_YEAR = "۱۴۰۴"

# ==================== مسیرها ====================
BASE_DIR = Path(__file__).parent
MAIN_SCRIPT = BASE_DIR / "kaveh_books1 - pic.py"
ASSETS_DIR = BASE_DIR / "assets"
PICS_DIR = BASE_DIR / "pics"
DB_FILE = BASE_DIR / "books_archive.db"

# آیکون‌ها
ICON_ICO = ASSETS_DIR / "icon.ico"
ICON_PNG = ASSETS_DIR / "icon.png"
LOGO_JPG = ASSETS_DIR / "logo.jpg"

# پوشه‌های ساخت
BUILD_DIR = BASE_DIR / "build"
DIST_DIR = BASE_DIR / "dist"
INSTALLER_DIR = BASE_DIR / "installer"


class InstallerBuilder:
    """کلاس اصلی برای ساخت Installer"""

    def __init__(self):
        self.start_time = time.time()
        self.setup_directories()

    def setup_directories(self):
        """ایجاد پوشه‌های لازم"""
        print("🔨 راه‌اندازی محیط ساخت...")

        for directory in [BUILD_DIR, DIST_DIR, INSTALLER_DIR]:
            directory.mkdir(exist_ok=True)

        # ایجاد پوشه‌های داخلی assets
        (ASSETS_DIR / "fonts").mkdir(parents=True, exist_ok=True)
        PICS_DIR.mkdir(exist_ok=True)

    def check_prerequisites(self):
        """بررسی پیش‌نیازها"""
        print("\n🔍 بررسی پیش‌نیازها...")

        # 1. بررسی فایل اصلی برنامه
        if not MAIN_SCRIPT.exists():
            raise FileNotFoundError(f"❌ فایل اصلی برنامه '{MAIN_SCRIPT.name}' یافت نشد!")

        # 2. بررسی آیکون‌ها
        if not ICON_ICO.exists():
            print("⚠️ هشدار: فایل icon.ico یافت نشد")
            if ICON_PNG.exists():
                print("🔄 تبدیل icon.png به icon.ico...")
                self.convert_png_to_ico()
            else:
                print("⚠️ هشدار: هیچ فایل آیکونی یافت نشد!")

        # 3. بررسی فونت فارسی
        font_file = ASSETS_DIR / "fonts" / "IRANSansX-Regular.ttf"
        if not font_file.exists():
            print("⚠️ هشدار: فونت فارسی یافت نشد!")
            print("   لطفاً فونت IRANSansX-Regular.ttf را در assets/fonts قرار دهید")

        # 4. بررسی پایگاه داده
        if not DB_FILE.exists():
            print("📝 ایجاد پایگاه داده اولیه...")
            self.create_initial_database()

        print("✅ بررسی پیش‌نیازها تکمیل شد")
        return True

    def convert_png_to_ico(self):
        """تبدیل PNG به ICO"""
        try:
            from PIL import Image

            img = Image.open(ICON_PNG)

            # ایجاد آیکون با سایزهای مختلف
            sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

            # ذخیره به صورت ICO
            img.save(ICON_ICO, format='ICO', sizes=sizes)
            print(f"✅ آیکون ایجاد شد: {ICON_ICO}")

        except ImportError:
            print("⚠️ Pillow نصب نیست. نصب با: pip install Pillow")
            return False
        except Exception as e:
            print(f"❌ خطا در ایجاد آیکون: {e}")
            return False

    def create_initial_database(self):
        """ایجاد پایگاه داده اولیه"""
        try:
            import sqlite3

            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()

            # ایجاد جداول اولیه
            cursor.executescript("""
                CREATE TABLE IF NOT EXISTS books (
                    id INTEGER PRIMARY KEY,
                    book_id INTEGER UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    brand TEXT,
                    model TEXT,
                    machine_type TEXT,
                    language TEXT,
                    edition_year TEXT,
                    location TEXT
                );

                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );

                INSERT INTO meta (key, value) VALUES 
                ('version', '1.0'),
                ('created', CURRENT_TIMESTAMP),
                ('developer', 'امیر فرشادفر'),
                ('company', 'شرکت خدمات دریایی و بندری کاوه');
            """)

            conn.commit()
            conn.close()
            print(f"✅ پایگاه داده اولیه ایجاد شد: {DB_FILE}")

        except Exception as e:
            print(f"⚠️ خطا در ایجاد پایگاه داده: {e}")

    def clean_previous_builds(self):
        """پاک کردن ساخت‌های قبلی"""
        print("\n🧹 پاک کردن ساخت‌های قبلی...")

        for folder in [BUILD_DIR, DIST_DIR]:
            if folder.exists():
                shutil.rmtree(folder)
                print(f"✅ پوشه {folder.name} پاک شد")

        # پاک کردن فایل‌های spec
        for spec_file in BASE_DIR.glob("*.spec"):
            spec_file.unlink()
            print(f"✅ فایل {spec_file.name} پاک شد")

    def build_executable(self):
        """ساخت فایل اجرایی با PyInstaller"""
        print("\n🚀 ساخت فایل اجرایی...")

        # آماده‌سازی دستور PyInstaller
        pyinstaller_args = [
            'pyinstaller',
            '--name', APP_NAME,
            '--windowed',  # پنجره‌ای (بدون کنسول)
            '--clean',
            '--onefile',  # تک فایل
            '--noconfirm',
            '--distpath', str(DIST_DIR),
            '--workpath', str(BUILD_DIR),
        ]

        # اضافه کردن آیکون
        if ICON_ICO.exists():
            pyinstaller_args.extend(['--icon', str(ICON_ICO)])

        # اضافه کردن فایل‌های داده
        pyinstaller_args.extend([
            '--add-data', f'{ASSETS_DIR}{os.pathsep}assets',
            '--add-data', f'{PICS_DIR}{os.pathsep}pics',
            '--add-data', f'{DB_FILE}{os.pathsep}.',
        ])

        # hidden imports
        hidden_imports = [
            'pandas', 'numpy', 'PIL', 'sqlite3',
            'PySide6', 'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets',
            'openpyxl', 'PIL._imaging', 'PIL._tkinter_finder'
        ]

        for imp in hidden_imports:
            pyinstaller_args.extend(['--hidden-import', imp])

        # اضافه کردن فایل اصلی
        pyinstaller_args.append(str(MAIN_SCRIPT))

        print(f"📦 اجرای PyInstaller با آرگومان‌ها...")

        try:
            result = subprocess.run(
                pyinstaller_args,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore'
            )

            if result.returncode == 0:
                # بررسی وجود فایل اجرایی
                exe_path = DIST_DIR / f"{APP_NAME}.exe"
                if exe_path.exists():
                    size_mb = exe_path.stat().st_size / (1024 * 1024)
                    print(f"✅ فایل اجرایی ایجاد شد: {exe_path}")
                    print(f"📊 حجم: {size_mb:.2f} MB")
                    return True
                else:
                    print("❌ فایل اجرایی ایجاد نشد!")
                    return False
            else:
                print(f"❌ خطا در PyInstaller:")
                print(result.stderr[:500])
                return False

        except Exception as e:
            print(f"❌ خطا در اجرای PyInstaller: {e}")
            return False

    def create_iss_script(self):
        """ایجاد فایل اسکریپت Inno Setup"""
        print("\n📝 ایجاد اسکریپت Inno Setup...")

        iss_content = f""";  ساخته شده توسط امیر فرشادفر
; برای برنامه: {PROJECT_NAME}

#define MyAppName "{PROJECT_NAME}"
#define MyAppVersion "{PROJECT_VERSION}"
#define MyAppPublisher "{COMPANY_NAME}"
#define MyAppDeveloper "{DEVELOPER}"
#define MyAppURL "ff"
#define MyAppExeName "{APP_NAME}.exe"
#define MyAppCopyright "© {COMPANY_NAME}"

[Setup]
AppId={{{{{APP_KEY}}}}}
AppName={{#MyAppName}}
AppVersion={{#MyAppVersion}}
AppVerName={{#MyAppName}} {{#MyAppVersion}}
AppPublisher={{#MyAppPublisher}}
AppPublisherURL={{#MyAppURL}}
AppSupportURL={{#MyAppURL}}
AppUpdatesURL={{#MyAppURL}}
AppCopyright={{#MyAppCopyright}}
AppContact={DEVELOPER}
DefaultDirName={{autopf}}\\{{#MyAppName}}
DefaultGroupName={{#MyAppName}}
AllowNoIcons=yes
LicenseFile=LICENSE.txt
OutputDir={INSTALLER_DIR}
OutputBaseFilename=KavehBooks_Setup_{PROJECT_VERSION}
SetupIconFile={ICON_ICO}
Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
MinVersion=10.0

[Languages]
Name: "persian"; MessagesFile: "compiler:Languages\\Persian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
persian.CreateDesktopIcon=ایجاد آیکون روی میزکار
persian.AdditionalIcons=آیکون‌های اضافی:

[Tasks]
Name: "desktopicon"; Description: "{{cm:CreateDesktopIcon}}"; \
    GroupDescription: "{{cm:AdditionalIcons}}"
Name: "quicklaunchicon"; Description: "ایجاد آیکون در نوار ابزار سریع"; \
    GroupDescription: "{{cm:AdditionalIcons}}"; Flags: unchecked

[Files]
; فایل اجرایی اصلی
Source: "{DIST_DIR}\\{APP_NAME}.exe"; DestDir: "{{app}}"; Flags: ignoreversion
; پایگاه داده
Source: "{DB_FILE}"; DestDir: "{{app}}"; Flags: ignoreversion
; پوشه assets
Source: "{ASSETS_DIR}\\*"; DestDir: "{{app}}\\assets"; \
    Flags: ignoreversion recursesubdirs createallsubdirs
; پوشه pics
Source: "{PICS_DIR}\\*"; DestDir: "{{app}}\\pics"; \
    Flags: ignoreversion recursesubdirs createallsubdirs
; فایل مجوز
Source: "LICENSE.txt"; DestDir: "{{app}}"; Flags: ignoreversion

[Icons]
Name: "{{group}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{#MyAppExeName}}"
Name: "{{group}}\\حذف نصب {{#MyAppName}}"; Filename: "{{uninstallexe}}"
Name: "{{commondesktop}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{#MyAppExeName}}"; \
    Tasks: desktopicon
Name: "{{userappdata}}\\Microsoft\\Internet Explorer\\Quick Launch\\{{#MyAppName}}"; \
    Filename: "{{app}}\\{{#MyAppExeName}}"; Tasks: quicklaunchicon

[Run]
Filename: "{{app}}\\{{#MyAppExeName}}"; \
    Description: "اجرای {{#MyAppName}}"; \
    Flags: nowait postinstall skipifsilent

[Registry]
; ثبت اطلاعات برنامه در رجیستری
Root: HKLM; Subkey: "Software\\{COMPANY_NAME}\\{{#MyAppName}}"; \
    ValueType: string; ValueName: "Version"; ValueData: "{{#MyAppVersion}}"; \
    Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\\{COMPANY_NAME}\\{{#MyAppName}}"; \
    ValueType: string; ValueName: "InstallPath"; ValueData: "{{app}}"; \
    Flags: uninsdeletekey

[Code]
// کدهای پاسکال برای تنظیمات اضافی

procedure CurPageChanged(CurPageID: Integer);
begin
  // پیش‌فرض Next بر اساس زبان انتخابی
  WizardForm.NextButton.Caption := SetupMessage(msgButtonNext);

  // صفحه آخر = Finish (باز هم بر اساس زبان)
  if CurPageID = wpFinished then
    WizardForm.NextButton.Caption := SetupMessage(msgButtonFinish);
end;

procedure InitializeWizard();
begin
  // فقط فونت (اختیاری)
  WizardForm.WelcomeLabel2.Font.Name := 'Tahoma';
  WizardForm.WelcomeLabel2.Font.Size := 10;
    // متن خوش‌آمدگویی فارسی
  WizardForm.WelcomeLabel2.Caption := 
    'به نصب‌کننده ' + '{{#MyAppName}}' + ' خوش آمدید.' + #13#10 +
    'این برنامه توسط ' + '{{#MyAppDeveloper}}' + #13#10 +
    'برای مدیریت آرشیو کتاب‌های فنی شرکت خدمات دریایی و بندری کاوه توسعه یافته است.' + #13#10 +
    'ویژگی‌های برنامه:' + #13#10 +
    '• مدیریت کتاب‌های فنی و منوال دستگاه‌ها' + #13#10 +
    '• نمایش لیستی و تصویری' + #13#10 +
    '• جستجو و فیلتر پیشرفته' + #13#10 +
    '• پشتیبانی از تصاویر کتاب‌ها' + #13#10 +
    'برای ادامه، روی دکمه "بعدی" کلیک کنید.';
end;







function InitializeSetup(): Boolean;
begin
  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // ایجاد پوشه‌های لازم
    ForceDirectories(ExpandConstant('{{app}}\\pics'));
    ForceDirectories(ExpandConstant('{{app}}\\assets\\fonts'));
  end;
end;
"""

        # ذخیره فایل ISS
        iss_file = BASE_DIR / "setup.iss"
        with open(iss_file, 'w', encoding='utf-8') as f:
            f.write(iss_content)

        print(f"✅ فایل ISS ایجاد شد: {iss_file}")

        # ایجاد فایل LICENSE.txt
        license_content = f"""مجوز استفاده از نرم‌افزار
{PROJECT_NAME} نسخه {PROJECT_VERSION}

این نرم‌افزار توسط {COMPANY_NAME} توسعه یافته است.
توسعه‌دهنده: {DEVELOPER}

حقوق نشر (کپی رایت):
امیر فرشادفر -  {COMPANY_NAME} {COPYRIGHT_YEAR}
کلیه حقوق محفوظ است.

شرایط استفاده:
1. این نرم‌افزار برای استفاده داخلی شرکت کاوه توسعه یافته است.
2. هرگونه کپی، توزیع یا تغییر بدون مجوز کتبی ممنوع است.
3. این نرم‌افزار "به همان صورت که هست" ارائه می‌شود.
4. شرکت کاوه مسئولیتی در قبال خسارات ناشی از استفاده از این نرم‌افزار ندارد.

برای اطلاعات بیشتر با بخش فنی شرکت تماس بگیرید.
"""

        license_file = BASE_DIR / "LICENSE.txt"
        with open(license_file, 'w', encoding='utf-8') as f:
            f.write(license_content)

        return True

    def compile_installer(self):
        """کامپایل Installer با Inno Setup"""
        print("\n⚙️ کامپایل Installer...")

        # یافتن ISCC.exe
        iscc_paths = [
            r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
            r"C:\Program Files\Inno Setup 6\ISCC.exe",
            r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
            r"C:\Program Files\Inno Setup 5\ISCC.exe",
        ]

        iscc_exe = None
        for path in iscc_paths:
            if os.path.exists(path):
                iscc_exe = path
                break

        if not iscc_exe:
            print("❌ Inno Setup یافت نشد!")
            print("لطفاً Inno Setup را از آدرس زیر دانلود و نصب کنید:")
            print("https://jrsoftware.org/isdl.php")
            print("سپس این اسکریپت را مجدداً اجرا کنید.")
            return False

        # کامپایل
        iss_file = BASE_DIR / "setup.iss"

        try:
            result = subprocess.run(
                [iscc_exe, str(iss_file)],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore'
            )

            if result.returncode == 0:
                print("✅ Installer با موفقیت کامپایل شد")

                # نمایش فایل ایجاد شده
                installer_files = list(INSTALLER_DIR.glob("*.exe"))
                if installer_files:
                    installer = installer_files[0]
                    size_mb = installer.stat().st_size / (1024 * 1024)
                    print(f"📦 فایل نصبی: {installer.name}")
                    print(f"📊 حجم: {size_mb:.2f} MB")
                    return True
                else:
                    print("⚠️ فایل Installer یافت نشد!")
                    return False
            else:
                print(f"❌ خطا در کامپایل:")
                print(result.stderr[:500])
                return False

        except Exception as e:
            print(f"❌ خطا در اجرای ISCC: {e}")
            return False

    def create_readme(self):
        """ایجاد فایل README"""
        print("\n📄 ایجاد مستندات...")

        readme_content = f"""📚 {PROJECT_NAME} - نسخه {PROJECT_VERSION}

📋 معرفی
برنامه مدیریت آرشیو کتاب‌های فنی شرکت خدمات دریایی و بندری کاوه

👨‍💼 توسعه‌دهنده: {DEVELOPER}
🏢 شرکت: {COMPANY_NAME}
📅 تاریخ انتشار: {time.strftime('%Y/%m/%d')}

🚀 ویژگی‌های برنامه
────────────────────
• مدیریت کتاب‌های فنی و منوال دستگاه‌ها
• نمایش لیستی و تصویری
• جستجو و فیلتر پیشرفته
• پشتیبانی از تصاویر کتاب‌ها
• خروجی CSV و Excel
• رابط کاربری فارسی و مدرن

🔧 نصب و راه‌اندازی
────────────────────
1. فایل 'KavehBooks_Setup_{PROJECT_VERSION}.exe' را اجرا کنید
2. مراحل نصب را دنبال کنید
3. برنامه از منوی استارت قابل اجراست

📁 ساختار پوشه نصب
────────────────────
{PROJECT_NAME}/
├── KavehBooks.exe              # فایل اجرایی
├── books_archive.db           # پایگاه داده
├── assets/                    # منابع گرافیکی
│   ├── fonts/                # فونت فارسی
│   ├── icon.ico              # آیکون برنامه
│   └── logo.jpg              # لوگوی شرکت
├── pics/                     # تصاویر کتاب‌ها
└── LICENSE.txt               # مجوز برنامه

🎮 راهنمای استفاده
────────────────────
1. اولین اجرا:
   - برنامه را اجرا کنید
   - از منوی "فایل → بازسازی از اکسل" استفاده کنید
   - فایل Excel کتاب‌ها را انتخاب کنید

2. افزودن تصاویر:
   - تصاویر را در پوشه 'pics' قرار دهید
   - نام فایل = شماره کتاب (مثال: 180.jpg)
   - برای چند تصویر: 180-1.jpg, 180-2.jpg

3. جستجو:
   - از پنل فیلتر در سمت چپ استفاده کنید
   - بر اساس برند، مدل، نوع و زبان فیلتر کنید

🛠️ عیب‌یابی
────────────────────
• مشکل فونت فارسی:
  - فونت IRANSansX در assets/fonts قرار دارد

• مشکل تصاویر:
  - مطمئن شوید پوشه pics وجود دارد
  - نام تصاویر با شماره کتاب مطابقت دارد

• خطای اجرا:
  - Visual C++ Redistributable را نصب کنید
  - برنامه را با Run as Administrator اجرا کنید

📞 پشتیبانی
────────────────────
شرکت خدمات دریایی و بندری کاوه
توسعه‌دهنده: {DEVELOPER}
ایمیل: amirfarshadfar1997@gmail.com

⚠️ نکات مهم
────────────────────
• این نرم‌افزار برای استفاده داخلی شرکت است
• از تغییر دستی فایل‌های دیتابیس خودداری کنید
• قبل از حذف نصب از اطلاعات پشتیبان بگیرید

امیر فرشادفر -   {COMPANY_NAME} {COPYRIGHT_YEAR}
کلیه حقوق محفوظ است.
"""

        readme_file = INSTALLER_DIR / "README.txt"
        with open(readme_file, 'w', encoding='utf-8') as f:
            f.write(readme_content)

        print(f"✅ فایل README ایجاد شد: {readme_file}")
        return True

    def calculate_hash(self, file_path):
        """محاسبه هش فایل"""
        with open(file_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()

    def run(self):
        """اجرای فرآیند ساخت"""
        try:
            print("=" * 70)
            print(f"🔨 شروع فرآیند ساخت Installer")
            print(f"📦 برنامه: {PROJECT_NAME}")
            print(f"🏷️  نسخه: {PROJECT_VERSION}")
            print(f"👨‍💼 توسعه‌دهنده: {DEVELOPER}")
            print("=" * 70)

            # 1. بررسی پیش‌نیازها
            if not self.check_prerequisites():
                return False

            # 2. پاکسازی ساخت‌های قبلی
            self.clean_previous_builds()

            # 3. ساخت EXE
            if not self.build_executable():
                return False

            # 4. ایجاد اسکریپت ISS
            self.create_iss_script()

            # 5. کامپایل Installer
            if not self.compile_installer():
                return False

            # 6. ایجاد مستندات
            self.create_readme()

            # محاسبه زمان اجرا
            elapsed = time.time() - self.start_time
            minutes = int(elapsed // 60)
            seconds = int(elapsed % 60)

            # نمایش نتیجه نهایی
            print("\n" + "=" * 70)
            print("🎉 ساخت Installer با موفقیت تکمیل شد!")
            print("=" * 70)
            print(f"⏱️  زمان اجرا: {minutes} دقیقه و {seconds} ثانیه")
            print(f"📁 پوشه خروجی: {INSTALLER_DIR}")
            print("\n📦 فایل‌های تولید شده:")

            # لیست فایل‌ها
            for file in sorted(INSTALLER_DIR.iterdir()):
                if file.is_file():
                    size_kb = file.stat().st_size / 1024
                    print(f"   📄 {file.name:40} ({size_kb:.1f} KB)")

            print("\n" + "=" * 70)
            print("🚀 مراحل نصب:")
            print("1. فایل نصبی را اجرا کنید (نیاز به Run as Administrator دارد)")
            print("2. مراحل نصب را طی کنید")
            print("3. برنامه از منوی Start > KavehBooks قابل اجراست")
            print("\n📞 پشتیبانی: با امیر فرشادفر تماس بگیرید")
            print("=" * 70)

            return True

        except Exception as e:
            print(f"\n❌ خطای غیرمنتظره: {e}")
            import traceback
            traceback.print_exc()
            return False


def main():
    """تابع اصلی"""
    builder = InstallerBuilder()

    if builder.run():
        print("\n✅ فرآیند ساخت با موفقیت انجام شد!")
        return 0
    else:
        print("\n❌ ساخت Installer ناموفق بود!")
        return 1


if __name__ == "__main__":
    sys.exit(main())