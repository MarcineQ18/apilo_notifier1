from typing import List, Optional
from db import get_conn


class SettingsRepo:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_table()

    def _ensure_table(self) -> None:
        conn = get_conn(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.commit()
        conn.close()

    # =========================
    # GENERIC
    # =========================
    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        conn = get_conn(self.db_path)
        row = conn.execute(
            "SELECT value FROM settings WHERE key=?",
            (key,),
        ).fetchone()
        conn.close()
        return row[0] if row else default

    def set(self, key: str, value: str) -> None:
        conn = get_conn(self.db_path)
        conn.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        conn.commit()
        conn.close()

    # =========================
    # STATUS
    # =========================
    def get_status_from_ids(self, default: List[int]) -> List[int]:
        raw = self.get("status_from_ids")
        if not raw:
            return default
        return [int(x) for x in raw.split(",") if x.strip().isdigit()]

    def set_status_from_ids(self, ids: List[int]) -> None:
        self.set("status_from_ids", ",".join(str(x) for x in ids))

    def get_status_to_id(self, default: int) -> int:
        raw = self.get("status_to_id")
        return int(raw) if raw and raw.isdigit() else default

    def set_status_to_id(self, status_id: int) -> None:
        self.set("status_to_id", str(int(status_id)))

    # =========================
    # APILO TOKENS
    # =========================
    def get_apilo_access_token(self) -> Optional[str]:
        return self.get("apilo_access_token")

    def get_apilo_refresh_token(self) -> Optional[str]:
        return self.get("apilo_refresh_token")

    def set_apilo_tokens(
        self,
        access_token: str,
        refresh_token: str,
        access_exp: Optional[str],
        refresh_exp: Optional[str],
    ) -> None:
        self.set("apilo_access_token", access_token)
        self.set("apilo_refresh_token", refresh_token)

        if access_exp:
            self.set("apilo_access_exp", access_exp)
        if refresh_exp:
            self.set("apilo_refresh_exp", refresh_exp)