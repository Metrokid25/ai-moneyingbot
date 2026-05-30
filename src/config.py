import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DEBUG_DIR = PROJECT_ROOT / "debug"
DB_PATH = DATA_DIR / "archive.db"

BROWSER_TIMEOUT_MS = int(os.getenv("BROWSER_TIMEOUT_MS", "30000"))
HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"
DEFAULT_BROWSER_PROFILE_DIR = Path(
    os.getenv("ARCHIVE_BROWSER_PROFILE_DIR", str(PROJECT_ROOT / "state" / "browser_profile"))
)
