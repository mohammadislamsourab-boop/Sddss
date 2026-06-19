"""Central configuration loaded from environment variables / .env file."""
import os

from dotenv import load_dotenv

load_dotenv()


def _parse_admin_ids(raw: str) -> set[int]:
    ids: set[int] = set()
    for part in (raw or "").replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids


BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS: set[int] = _parse_admin_ids(os.getenv("ADMIN_IDS", ""))

STORE_NAME: str = os.getenv("STORE_NAME", "GPTCheap Store").strip()
SUPPORT_USERNAME: str = os.getenv("SUPPORT_USERNAME", "@support").strip()

BINANCE_ID: str = os.getenv("BINANCE_ID", "459182587").strip()
USDT_BEP20_ADDRESS: str = os.getenv(
    "USDT_BEP20_ADDRESS", "0x0000000000000000000000000000000000000000"
).strip()

CURRENCY: str = os.getenv("CURRENCY", "$").strip()
DB_PATH: str = os.getenv("DB_PATH", "data/store.db").strip()

# Buyers may purchase between 1 and this many units per order.
MAX_QUANTITY_PER_ORDER: int = int(os.getenv("MAX_QUANTITY_PER_ORDER", "3"))


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def money(amount: float) -> str:
    """Format an amount with the configured currency symbol."""
    return f"{CURRENCY}{amount:,.2f}"
