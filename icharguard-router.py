import os
import sys

BROKER_HOST = os.environ.get("BROKER_HOST", "localhost")
BROKER_PORT = int(os.environ.get("BROKER_PORT", "1883"))
BROKER_WS_PORT = int(os.environ.get("BROKER_WS_PORT", "9001"))

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)

from src.router import config  # noqa: E402

config.BROKER_HOST = BROKER_HOST
config.BROKER_PORT = BROKER_PORT
config.BROKER_WS_PORT = BROKER_WS_PORT
config.SCRIPT_DIR = _SCRIPT_DIR
config.DB_FILE = os.path.join(_SCRIPT_DIR, "icharguard.db")

from src.router.main import run  # noqa: E402

run()
