"""SQLite data-access layer for the auto-order store bot.

All persistence lives here so the handler code stays focused on Telegram
interaction. The schema is created automatically on first run.
"""
from __future__ import annotations

import os
import random
import sqlite3
import string
import time
from contextlib import contextmanager
from typing import Iterable, Optional

import config

# Order lifecycle states.
STATUS_AWAITING_PAYMENT = "awaiting_payment"   # waiting for buyer to pay (off-chain)
STATUS_AWAITING_REVIEW = "awaiting_review"     # buyer submitted tx ref, admin must confirm
STATUS_COMPLETED = "completed"                 # delivered
STATUS_CANCELLED = "cancelled"

# Wallet ledger entry types.
TX_TOPUP = "topup"
TX_PURCHASE = "purchase"
TX_REFUND = "refund"
TX_ADMIN = "admin_adjust"


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(config.DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_conn():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                first_name  TEXT,
                balance     REAL NOT NULL DEFAULT 0,
                created_at  INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS products (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                emoji       TEXT DEFAULT '',
                name        TEXT NOT NULL,
                description TEXT DEFAULT '',
                price       REAL NOT NULL,
                image_url   TEXT DEFAULT '',
                sold        INTEGER NOT NULL DEFAULT 0,
                is_active   INTEGER NOT NULL DEFAULT 1,
                position    INTEGER NOT NULL DEFAULT 0,
                created_at  INTEGER NOT NULL
            );

            -- One row == one deliverable unit (account credentials, key, etc.)
            CREATE TABLE IF NOT EXISTS stock (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id  INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                content     TEXT NOT NULL,
                is_sold     INTEGER NOT NULL DEFAULT 0,
                sold_to     INTEGER,
                order_id    INTEGER,
                added_at    INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS orders (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                code        TEXT NOT NULL UNIQUE,
                user_id     INTEGER NOT NULL,
                product_id  INTEGER NOT NULL,
                product_name TEXT NOT NULL,
                quantity    INTEGER NOT NULL,
                total       REAL NOT NULL,
                method      TEXT NOT NULL,
                status      TEXT NOT NULL,
                tx_ref      TEXT DEFAULT '',
                delivered   TEXT DEFAULT '',
                created_at  INTEGER NOT NULL,
                updated_at  INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                amount      REAL NOT NULL,
                type        TEXT NOT NULL,
                note        TEXT DEFAULT '',
                created_at  INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_stock_product ON stock(product_id, is_sold);
            CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
            CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
            """
        )


# --------------------------------------------------------------------------- #
# Users / wallet
# --------------------------------------------------------------------------- #
def upsert_user(user_id: int, username: Optional[str], first_name: Optional[str]) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO users (user_id, username, first_name, balance, created_at)
            VALUES (?, ?, ?, 0, ?)
            ON CONFLICT(user_id) DO UPDATE SET username=excluded.username,
                                               first_name=excluded.first_name
            """,
            (user_id, username, first_name, int(time.time())),
        )


def get_user(user_id: int) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()


def get_balance(user_id: int) -> float:
    row = get_user(user_id)
    return float(row["balance"]) if row else 0.0


def adjust_balance(user_id: int, amount: float, tx_type: str, note: str = "") -> float:
    """Add (or subtract) `amount` from a user's balance and record the ledger entry.

    Returns the new balance.
    """
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO users (user_id, balance, created_at) VALUES (?, 0, ?)
            ON CONFLICT(user_id) DO NOTHING
            """,
            (user_id, int(time.time())),
        )
        conn.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
            (amount, user_id),
        )
        conn.execute(
            "INSERT INTO transactions (user_id, amount, type, note, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, tx_type, note, int(time.time())),
        )
        row = conn.execute(
            "SELECT balance FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return float(row["balance"])


def list_transactions(user_id: int, limit: int = 10) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM transactions WHERE user_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()


# --------------------------------------------------------------------------- #
# Products / stock
# --------------------------------------------------------------------------- #
def add_product(
    name: str,
    price: float,
    emoji: str = "",
    description: str = "",
    image_url: str = "",
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO products (emoji, name, description, price, image_url, "
            "position, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (emoji, name, description, price, image_url, int(time.time()),
             int(time.time())),
        )
        return cur.lastrowid


def update_product(product_id: int, **fields) -> None:
    allowed = {"emoji", "name", "description", "price", "image_url",
               "is_active", "position"}
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return
    cols = ", ".join(f"{k} = ?" for k in sets)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE products SET {cols} WHERE id = ?",
            (*sets.values(), product_id),
        )


def get_product(product_id: int) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM products WHERE id = ?", (product_id,)
        ).fetchone()


def list_products(active_only: bool = True) -> list[sqlite3.Row]:
    with get_conn() as conn:
        query = "SELECT * FROM products"
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY position DESC, id ASC"
        return conn.execute(query).fetchall()


def stock_count(product_id: int) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM stock WHERE product_id = ? AND is_sold = 0",
            (product_id,),
        ).fetchone()
        return int(row["c"])


def add_stock_items(product_id: int, items: Iterable[str]) -> int:
    now = int(time.time())
    rows = [(product_id, item.strip(), now) for item in items if item.strip()]
    if not rows:
        return 0
    with get_conn() as conn:
        conn.executemany(
            "INSERT INTO stock (product_id, content, added_at) VALUES (?, ?, ?)",
            rows,
        )
    return len(rows)


def reserve_and_deliver_stock(
    product_id: int, quantity: int, user_id: int, order_id: int
) -> Optional[list[str]]:
    """Atomically mark `quantity` unsold stock rows as sold and return contents.

    Returns None if there is not enough stock (no changes made).
    """
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, content FROM stock WHERE product_id = ? AND is_sold = 0 "
            "ORDER BY id ASC LIMIT ?",
            (product_id, quantity),
        ).fetchall()
        if len(rows) < quantity:
            return None
        ids = [r["id"] for r in rows]
        conn.executemany(
            "UPDATE stock SET is_sold = 1, sold_to = ?, order_id = ? WHERE id = ?",
            [(user_id, order_id, sid) for sid in ids],
        )
        conn.execute(
            "UPDATE products SET sold = sold + ? WHERE id = ?",
            (quantity, product_id),
        )
        return [r["content"] for r in rows]


# --------------------------------------------------------------------------- #
# Orders
# --------------------------------------------------------------------------- #
def _generate_order_code() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=10))
    return f"ORDER{suffix}"


def create_order(
    user_id: int,
    product_id: int,
    product_name: str,
    quantity: int,
    total: float,
    method: str,
    status: str,
) -> sqlite3.Row:
    now = int(time.time())
    with get_conn() as conn:
        # Retry a few times in the (very unlikely) event of a code collision.
        for _ in range(5):
            code = _generate_order_code()
            try:
                cur = conn.execute(
                    "INSERT INTO orders (code, user_id, product_id, product_name, "
                    "quantity, total, method, status, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (code, user_id, product_id, product_name, quantity, total,
                     method, status, now, now),
                )
                break
            except sqlite3.IntegrityError:
                continue
        else:
            raise RuntimeError("Could not generate a unique order code")
        return conn.execute(
            "SELECT * FROM orders WHERE id = ?", (cur.lastrowid,)
        ).fetchone()


def get_order_by_code(code: str) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM orders WHERE code = ?", (code.strip(),)
        ).fetchone()


def get_order(order_id: int) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM orders WHERE id = ?", (order_id,)
        ).fetchone()


def set_order_status(order_id: int, status: str, **fields) -> None:
    allowed = {"tx_ref", "delivered"}
    sets = {k: v for k, v in fields.items() if k in allowed}
    cols = "".join(f", {k} = ?" for k in sets)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE orders SET status = ?, updated_at = ?{cols} WHERE id = ?",
            (status, int(time.time()), *sets.values(), order_id),
        )


def list_orders(user_id: Optional[int] = None, status: Optional[str] = None,
                limit: int = 20) -> list[sqlite3.Row]:
    clauses, params = [], []
    if user_id is not None:
        clauses.append("user_id = ?")
        params.append(user_id)
    if status is not None:
        clauses.append("status = ?")
        params.append(status)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    with get_conn() as conn:
        return conn.execute(
            f"SELECT * FROM orders{where} ORDER BY id DESC LIMIT ?", params
        ).fetchall()


# --------------------------------------------------------------------------- #
# Stats (admin dashboard)
# --------------------------------------------------------------------------- #
def stats() -> dict:
    with get_conn() as conn:
        users = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        products = conn.execute(
            "SELECT COUNT(*) c FROM products WHERE is_active = 1"
        ).fetchone()["c"]
        completed = conn.execute(
            "SELECT COUNT(*) c FROM orders WHERE status = ?",
            (STATUS_COMPLETED,),
        ).fetchone()["c"]
        revenue = conn.execute(
            "SELECT COALESCE(SUM(total), 0) s FROM orders WHERE status = ?",
            (STATUS_COMPLETED,),
        ).fetchone()["s"]
        pending = conn.execute(
            "SELECT COUNT(*) c FROM orders WHERE status = ?",
            (STATUS_AWAITING_REVIEW,),
        ).fetchone()["c"]
        return {
            "users": users,
            "products": products,
            "completed_orders": completed,
            "revenue": float(revenue),
            "pending_review": pending,
        }
