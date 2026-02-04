import json
from typing import List, Optional
from db import get_conn


class SettingsRepo:
    """
    app_settings:
    - poll_status_from_ids: JSON lista intów
    - poll_status_to_id: int (0 = nie zmieniaj statusu)
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure()

    def _ensure(self) -> None:
        conn = get_conn(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()

    def set(self, key: str, value: str) -> None:
        conn = get_conn(self.db_path)
        conn.execute("""
            INSERT INTO app_settings(key, value) VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """, (key, value))
        conn.commit()
        conn.close()

    def get(self, key: str) -> Optional[str]:
        conn = get_conn(self.db_path)
        row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
        conn.close()
        return row["value"] if row else None

    def set_status_from_ids(self, ids: List[int]) -> None:
        ids = [int(x) for x in ids if str(x).strip()]
        self.set("poll_status_from_ids", json.dumps(ids))

    def get_status_from_ids(self, default: List[int]) -> List[int]:
        raw = self.get("poll_status_from_ids")
        if not raw:
            return [int(x) for x in default]
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [int(x) for x in data]
        except Exception:
            pass
        return [int(x) for x in default]

    def set_status_to_id(self, status_id: int) -> None:
        self.set("poll_status_to_id", str(int(status_id)))

    def get_status_to_id(self, default: int) -> int:
        raw = self.get("poll_status_to_id")
        if raw is None or raw == "":
            return int(default)
        try:
            return int(raw)
        except Exception:
            return int(default)
