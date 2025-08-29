# main.py
import os, sys
from pathlib import Path
from streamlit.web import bootstrap

# --- خاموش کردن حالت Dev Frontend ---
for var in ["STREAMLIT_DEV", "STREAMLIT_FRONTEND_DEV_SERVER", "STREAMLIT_SERVER_DEV", "NODE_ENV"]:
    os.environ.pop(var, None)
os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"] = "false"

# --- تنظیمات سرور و مرورگر ---
os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"
os.environ["STREAMLIT_SERVER_ADDRESS"] = "localhost"
os.environ["STREAMLIT_SERVER_PORT"] = "8501"
os.environ["STREAMLIT_BROWSER_SERVER_ADDRESS"] = "localhost"
os.environ["STREAMLIT_BROWSER_SERVER_PORT"] = "8501"
os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"

# ⚠️ یا هر دو CORS/XSRF را True بذار (حالت امن‌تر):
os.environ["STREAMLIT_SERVER_ENABLECORS"] = "true"
os.environ["STREAMLIT_SERVER_ENABLEXSRFPROTECTION"] = "true"
# اگر می‌خوای Cross-Origin آزاد باشه، هر دو رو false کن:
# os.environ["STREAMLIT_SERVER_ENABLECORS"] = "false"
# os.environ["STREAMLIT_SERVER_ENABLEXSRFPROTECTION"] = "false"

def resource_path(rel: str) -> str:
    """دریافت مسیر درست چه در حالت exe چه در حالت dev"""
    base = Path(sys.argv[0]).resolve().parent
    return str(base / rel)

APP_FILE = resource_path("app_one_tab_pro.py")

if __name__ == "__main__":
    flags = {
        "global.developmentMode": False,  # کلید مهم
        "server.headless": True,
        "server.address": "localhost",
        "server.port": 8501,
        "server.fileWatcherType": "none",
        "browser.gatherUsageStats": False,
    }
    bootstrap.run(APP_FILE, "", [], flag_options=flags)
