from typing import List, Dict, Any, Optional
from db import get_conn


class TemplatesRepo:
    def __init__(self, db_path: str):
        self.db_path = db_path

    # =========================
    # EMAIL
    # =========================
    def list_templates_with_skus(self) -> List[Dict[str, Any]]:
        conn = get_conn(self.db_path)
        rows = conn.execute("""
            SELECT
                t.id, t.template_key, t.name, t.subject, t.body, t.is_html,
                t.priority, t.is_active, t.updated_at,
                GROUP_CONCAT(s.sku) AS skus
            FROM email_templates t
            LEFT JOIN email_template_skus s ON s.template_id = t.id
            GROUP BY t.id
            ORDER BY t.priority ASC, t.updated_at DESC
        """).fetchall()
        conn.close()

        out = []
        for r in rows:
            d = dict(r)
            d["skus"] = [x for x in (d.get("skus") or "").split(",") if x] if d.get("skus") else []
            d["is_active"] = int(d.get("is_active") or 0)
            out.append(d)
        return out

    def get_template(self, template_id: int) -> Optional[Dict[str, Any]]:
        conn = get_conn(self.db_path)
        row = conn.execute("""
            SELECT
                t.id, t.template_key, t.name, t.subject, t.body, t.is_html,
                t.priority, t.is_active, t.updated_at,
                GROUP_CONCAT(s.sku) AS skus
            FROM email_templates t
            LEFT JOIN email_template_skus s ON s.template_id = t.id
            WHERE t.id=?
            GROUP BY t.id
        """, (int(template_id),)).fetchone()
        conn.close()
        if not row:
            return None
        d = dict(row)
        d["skus"] = [x for x in (d.get("skus") or "").split(",") if x] if d.get("skus") else []
        d["is_active"] = int(d.get("is_active") or 0)
        return d

    def upsert(self, template_key: str, name: str, subject: str, body: str, is_html: int, priority: int = 100, is_active: int = 1):
        conn = get_conn(self.db_path)
        conn.execute("""
            INSERT INTO email_templates (template_key, name, subject, body, is_html, priority, is_active, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(template_key) DO UPDATE SET
                name=excluded.name,
                subject=excluded.subject,
                body=excluded.body,
                is_html=excluded.is_html,
                priority=excluded.priority,
                is_active=excluded.is_active,
                updated_at=datetime('now')
        """, (template_key, name, subject, body, int(is_html), int(priority), int(is_active)))
        conn.commit()
        conn.close()

    def update_by_id(self, template_id: int, name: str, subject: str, body: str, is_html: int, priority: int = 100, is_active: int = 1):
        conn = get_conn(self.db_path)
        conn.execute("""
            UPDATE email_templates
            SET name=?, subject=?, body=?, is_html=?, priority=?, is_active=?, updated_at=datetime('now')
            WHERE id=?
        """, (name, subject, body, int(is_html), int(priority), int(is_active), int(template_id)))
        conn.commit()
        conn.close()

    def delete_template(self, template_id: int):
        conn = get_conn(self.db_path)
        conn.execute("DELETE FROM email_templates WHERE id=?", (int(template_id),))
        conn.execute("DELETE FROM email_template_skus WHERE template_id=?", (int(template_id),))
        conn.commit()
        conn.close()

    def set_template_skus(self, template_id: int, skus: List[str]):
        conn = get_conn(self.db_path)
        conn.execute("DELETE FROM email_template_skus WHERE template_id=?", (int(template_id),))
        for sku in skus:
            sku = sku.strip()
            if sku:
                conn.execute(
                    "INSERT OR IGNORE INTO email_template_skus (template_id, sku) VALUES (?, ?)",
                    (int(template_id), sku)
                )
        conn.commit()
        conn.close()

    # =========================
    # SMS
    # =========================
    def list_sms_templates_with_skus(self) -> List[Dict[str, Any]]:
        conn = get_conn(self.db_path)
        rows = conn.execute("""
            SELECT
                t.id, t.template_key, t.name, t.body,
                t.priority, t.is_active, t.updated_at,
                GROUP_CONCAT(s.sku) AS skus
            FROM sms_templates t
            LEFT JOIN sms_template_skus s ON s.template_id = t.id
            GROUP BY t.id
            ORDER BY t.priority ASC, t.updated_at DESC
        """).fetchall()
        conn.close()

        out = []
        for r in rows:
            d = dict(r)
            d["skus"] = [x for x in (d.get("skus") or "").split(",") if x] if d.get("skus") else []
            d["is_active"] = int(d.get("is_active") or 0)
            out.append(d)
        return out

    def get_sms_template(self, template_id: int) -> Optional[Dict[str, Any]]:
        conn = get_conn(self.db_path)
        row = conn.execute("""
            SELECT
                t.id, t.template_key, t.name, t.body,
                t.priority, t.is_active, t.updated_at,
                GROUP_CONCAT(s.sku) AS skus
            FROM sms_templates t
            LEFT JOIN sms_template_skus s ON s.template_id = t.id
            WHERE t.id=?
            GROUP BY t.id
        """, (int(template_id),)).fetchone()
        conn.close()
        if not row:
            return None
        d = dict(row)
        d["skus"] = [x for x in (d.get("skus") or "").split(",") if x] if d.get("skus") else []
        d["is_active"] = int(d.get("is_active") or 0)
        return d

    def upsert_sms(self, template_key: str, name: str, body: str, priority: int = 100, is_active: int = 1):
        conn = get_conn(self.db_path)
        conn.execute("""
            INSERT INTO sms_templates (template_key, name, body, priority, is_active, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(template_key) DO UPDATE SET
                name=excluded.name,
                body=excluded.body,
                priority=excluded.priority,
                is_active=excluded.is_active,
                updated_at=datetime('now')
        """, (template_key, name, body, int(priority), int(is_active)))
        conn.commit()
        conn.close()

    def update_sms_by_id(self, template_id: int, name: str, body: str, priority: int = 100, is_active: int = 1):
        conn = get_conn(self.db_path)
        conn.execute("""
            UPDATE sms_templates
            SET name=?, body=?, priority=?, is_active=?, updated_at=datetime('now')
            WHERE id=?
        """, (name, body, int(priority), int(is_active), int(template_id)))
        conn.commit()
        conn.close()

    def delete_sms_template(self, template_id: int):
        conn = get_conn(self.db_path)
        conn.execute("DELETE FROM sms_templates WHERE id=?", (int(template_id),))
        conn.execute("DELETE FROM sms_template_skus WHERE template_id=?", (int(template_id),))
        conn.commit()
        conn.close()

    def set_sms_template_skus(self, template_id: int, skus: List[str]):
        conn = get_conn(self.db_path)
        conn.execute("DELETE FROM sms_template_skus WHERE template_id=?", (int(template_id),))
        for sku in skus:
            sku = sku.strip()
            if sku:
                conn.execute(
                    "INSERT OR IGNORE INTO sms_template_skus (template_id, sku) VALUES (?, ?)",
                    (int(template_id), sku)
                )
        conn.commit()
        conn.close()

    # =========================
    # DEDUPE
    # =========================
    def mark_email_sent_if_new(self, order_id: str, template_id: int) -> bool:
        conn = get_conn(self.db_path)
        try:
            conn.execute("INSERT INTO email_sent_log(order_id, template_id) VALUES(?, ?)", (str(order_id), int(template_id)))
            conn.commit()
            return True
        except Exception:
            return False
        finally:
            conn.close()

    def mark_sms_sent_if_new(self, order_id: str, template_id: int) -> bool:
        conn = get_conn(self.db_path)
        try:
            conn.execute("INSERT INTO sms_sent_log(order_id, template_id) VALUES(?, ?)", (str(order_id), int(template_id)))
            conn.commit()
            return True
        except Exception:
            return False
        finally:
            conn.close()

    # =========================
    # MATCHING (poller)
    # =========================
    def match_email_templates_for_skus(self, order_skus: List[str]) -> List[Dict[str, Any]]:
        """
        - bierze tylko aktywne
        - puste SKU = do wszystkich
        - dopasowane po SKU
        """
        items = [t for t in self.list_templates_with_skus() if int(t.get("is_active") or 0) == 1]
        order_set = set(order_skus)

        matched = []
        for t in items:
            tpl_skus = set(t.get("skus") or [])
            if not tpl_skus:
                matched.append(t)
            elif tpl_skus & order_set:
                matched.append(t)

        matched.sort(key=lambda x: int(x.get("priority") or 100))
        return matched

    def match_sms_templates_for_skus(self, order_skus: List[str]) -> List[Dict[str, Any]]:
        items = [t for t in self.list_sms_templates_with_skus() if int(t.get("is_active") or 0) == 1]
        order_set = set(order_skus)

        matched = []
        for t in items:
            tpl_skus = set(t.get("skus") or [])
            if not tpl_skus:
                matched.append(t)
            elif tpl_skus & order_set:
                matched.append(t)

        matched.sort(key=lambda x: int(x.get("priority") or 100))
        return matched
