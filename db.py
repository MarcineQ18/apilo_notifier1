import os
import sqlite3


def ensure_dirs(db_path: str) -> None:
    folder = os.path.dirname(db_path)
    if folder:
        os.makedirs(folder, exist_ok=True)


def get_conn(db_path: str) -> sqlite3.Connection:
    ensure_dirs(db_path)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # FK ON
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _col_exists(conn: sqlite3.Connection, table: str, col: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == col for r in rows)


def init_db(db_path: str) -> None:
    conn = get_conn(db_path)
    cur = conn.cursor()

    # =========================
    # EMAIL
    # =========================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS email_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        template_key TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        subject TEXT NOT NULL DEFAULT '',
        body TEXT NOT NULL,
        is_html INTEGER NOT NULL DEFAULT 0,
        priority INTEGER NOT NULL DEFAULT 100,
        is_active INTEGER NOT NULL DEFAULT 1,
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS email_template_skus (
        template_id INTEGER NOT NULL,
        sku TEXT NOT NULL,
        PRIMARY KEY (template_id, sku),
        FOREIGN KEY (template_id) REFERENCES email_templates(id) ON DELETE CASCADE
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_email_template_skus_sku ON email_template_skus(sku)")

    # =========================
    # SMS
    # =========================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sms_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        template_key TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        body TEXT NOT NULL,
        priority INTEGER NOT NULL DEFAULT 100,
        is_active INTEGER NOT NULL DEFAULT 1,
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS sms_template_skus (
        template_id INTEGER NOT NULL,
        sku TEXT NOT NULL,
        PRIMARY KEY (template_id, sku),
        FOREIGN KEY (template_id) REFERENCES sms_templates(id) ON DELETE CASCADE
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sms_template_skus_sku ON sms_template_skus(sku)")

    # =========================
    # DEDUPE (żeby ten sam template nie poszedł 2x dla tego samego zamówienia)
    # =========================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS email_sent_log (
        order_id TEXT NOT NULL,
        template_id INTEGER NOT NULL,
        sent_at TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (order_id, template_id)
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sms_sent_log (
        order_id TEXT NOT NULL,
        template_id INTEGER NOT NULL,
        sent_at TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (order_id, template_id)
    )
    """)

    # =========================
    # MIGRACJE “na żywo” (jeśli DB już istnieje)
    # =========================
    # email_templates.is_active
    if not _col_exists(conn, "email_templates", "is_active"):
        cur.execute("ALTER TABLE email_templates ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")

    # sms_templates.is_active
    if not _col_exists(conn, "sms_templates", "is_active"):
        cur.execute("ALTER TABLE sms_templates ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")

    conn.commit()
    conn.close()
