import sqlite3
import os
from datetime import datetime
from contextlib import contextmanager
import configs


@contextmanager
def get_connection():
    os.makedirs(os.path.dirname(configs.DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(configs.DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize_database() -> None:
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id     INTEGER PRIMARY KEY,
                name            TEXT    NOT NULL,
                balance         REAL    NOT NULL DEFAULT 0.0,
                referred_by     INTEGER,
                created_at      TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS purchases (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL REFERENCES users(telegram_id),
                activation_id   TEXT,
                phone_number    TEXT,
                service         TEXT    NOT NULL,
                country         TEXT    NOT NULL,
                price_brl       REAL    NOT NULL,
                purchased_at    TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS payments (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id     TEXT    NOT NULL UNIQUE,
                user_id         INTEGER NOT NULL REFERENCES users(telegram_id),
                amount          REAL    NOT NULL,
                method          TEXT    NOT NULL,
                status          TEXT    NOT NULL DEFAULT 'pending',
                created_at      TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_purchases_user  ON purchases(user_id);
            CREATE INDEX IF NOT EXISTS idx_payments_user   ON payments(user_id);
            CREATE INDEX IF NOT EXISTS idx_payments_ext    ON payments(external_id);
        """)


# ── Usuários ──────────────────────────────────────────────────────────────────

def get_or_create_user(telegram_id: int, name: str) -> sqlite3.Row:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (telegram_id, name, balance, created_at)
            VALUES (?, ?, 0.0, ?)
            ON CONFLICT(telegram_id) DO NOTHING
            """,
            (telegram_id, name, datetime.now().isoformat()),
        )
    return get_user(telegram_id)


def get_user(telegram_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()


def credit_balance(telegram_id: int, amount: float) -> bool:
    with get_connection() as conn:
        result = conn.execute(
            "UPDATE users SET balance = balance + ? WHERE telegram_id = ?",
            (amount, telegram_id),
        )
    return result.rowcount > 0


def debit_balance(telegram_id: int, amount: float) -> bool:
    with get_connection() as conn:
        result = conn.execute(
            """
            UPDATE users SET balance = balance - ?
            WHERE telegram_id = ? AND balance >= ?
            """,
            (amount, telegram_id, amount),
        )
    return result.rowcount > 0


def set_referred_by(telegram_id: int, referrer_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET referred_by = ? WHERE telegram_id = ? AND referred_by IS NULL",
            (referrer_id, telegram_id),
        )


def count_referrals(telegram_id: int) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM users WHERE referred_by = ?", (telegram_id,)
        ).fetchone()
    return row[0]


# ── Compras ───────────────────────────────────────────────────────────────────

def save_purchase(
    user_id: int,
    activation_id: str,
    phone_number: str,
    service: str,
    country: str,
    price_brl: float,
) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO purchases
                (user_id, activation_id, phone_number, service, country, price_brl, purchased_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, activation_id, phone_number, service, country, price_brl,
             datetime.now().isoformat()),
        )
    return cursor.lastrowid


def get_last_purchase(user_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM purchases WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()


# ── Pagamentos ────────────────────────────────────────────────────────────────

def register_payment(
    external_id: str,
    user_id: int,
    amount: float,
    method: str,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO payments (external_id, user_id, amount, method, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (external_id, user_id, amount, method, datetime.now().isoformat()),
        )


def get_payment(external_id: str) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM payments WHERE external_id = ?", (external_id,)
        ).fetchone()


def list_pending_payments(method: str = "pix") -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM payments WHERE status = 'pending' AND method = ?",
            (method,),
        ).fetchall()


def update_payment_status(external_id: str, status: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE payments SET status = ? WHERE external_id = ?",
            (status, external_id),
        )
