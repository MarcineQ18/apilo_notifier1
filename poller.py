import time
from typing import Any, Dict, Optional, List

from apilo_client import ApiloClient
from mailer import Mailer
from processed_store import ProcessedStore
from web.templates_repo import TemplatesRepo
from sms_sender import SmsPlanetSender
from db import get_conn
from web.settings_repo import SettingsRepo
from settings import STATUS_FROM, STATUS_TO


def extract_payment_id(order_details: Dict[str, Any]) -> str:
    payments = order_details.get("orderPayments") or []
    if not payments:
        return "brak"
    p0 = payments[0] or {}
    return p0.get("idExternal") or str(p0.get("id") or "brak")


def extract_customer_email(order_details: Dict[str, Any]) -> Optional[str]:
    addr = order_details.get("addressCustomer") or {}
    return addr.get("email")


def extract_customer_phone(order_details: Dict[str, Any]) -> Optional[str]:
    addr = order_details.get("addressCustomer") or {}
    return addr.get("phone") or addr.get("phoneNumber")


def extract_skus(order_details: Dict[str, Any]) -> List[str]:
    items: List[Any] = []
    for key in ("orderItems", "orderProducts", "products", "items", "orderProduct"):
        arr = order_details.get(key)
        if isinstance(arr, list):
            items.extend(arr)

    out: List[str] = []
    seen = set()

    for it in items:
        if not isinstance(it, dict):
            continue
        sku = it.get("sku") or it.get("productSku") or it.get("code") or it.get("symbol")
        if not sku:
            continue
        sku = str(sku).strip()
        if sku and sku not in seen:
            seen.add(sku)
            out.append(sku)

    return out


def safe_format(text: str, data: Dict[str, Any]) -> str:
    class SafeDict(dict):
        def __missing__(self, key):
            return "{" + key + "}"
    return str(text or "").format_map(SafeDict(**data))


class Poller:
    def __init__(
        self,
        apilo: ApiloClient,
        mailer: Mailer,
        templates: TemplatesRepo,
        processed: ProcessedStore,
        poll_seconds: int,
        dry_run: bool,
        db_path: str,
        sms_sender: Optional[SmsPlanetSender] = None,
    ):
        self.apilo = apilo
        self.mailer = mailer
        self.templates = templates
        self.processed = processed
        self.poll_seconds = int(poll_seconds)
        self.dry_run = bool(dry_run)
        self.sms_sender = sms_sender
        self.settings = SettingsRepo(db_path=db_path)

    # =========================================
    # DEDUPE TABLES (wysłane szablony per order)
    # =========================================
    def _ensure_send_tables(self) -> None:
        conn = get_conn(self.templates.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS email_sends (
                order_id TEXT NOT NULL,
                template_id INTEGER NOT NULL,
                sent_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (order_id, template_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sms_sends (
                order_id TEXT NOT NULL,
                template_id INTEGER NOT NULL,
                sent_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (order_id, template_id)
            )
        """)
        conn.commit()
        conn.close()

    def _was_email_sent(self, order_id: str, template_id: int) -> bool:
        conn = get_conn(self.templates.db_path)
        row = conn.execute(
            "SELECT 1 FROM email_sends WHERE order_id=? AND template_id=? LIMIT 1",
            (str(order_id), int(template_id)),
        ).fetchone()
        conn.close()
        return row is not None

    def _mark_email_sent(self, order_id: str, template_id: int) -> None:
        conn = get_conn(self.templates.db_path)
        conn.execute(
            "INSERT OR IGNORE INTO email_sends(order_id, template_id) VALUES (?, ?)",
            (str(order_id), int(template_id)),
        )
        conn.commit()
        conn.close()

    def _was_sms_sent(self, order_id: str, template_id: int) -> bool:
        conn = get_conn(self.templates.db_path)
        row = conn.execute(
            "SELECT 1 FROM sms_sends WHERE order_id=? AND template_id=? LIMIT 1",
            (str(order_id), int(template_id)),
        ).fetchone()
        conn.close()
        return row is not None

    def _mark_sms_sent(self, order_id: str, template_id: int) -> None:
        conn = get_conn(self.templates.db_path)
        conn.execute(
            "INSERT OR IGNORE INTO sms_sends(order_id, template_id) VALUES (?, ?)",
            (str(order_id), int(template_id)),
        )
        conn.commit()
        conn.close()

    # =========================================
    # MAIN LOOP
    # =========================================
    def run_forever(self) -> None:
        self._ensure_send_tables()

        done = self.processed.load()
        print(f"Start pollera. DRY_RUN={self.dry_run}")

        while True:
            try:
                status_from_ids = self.settings.get_status_from_ids(default=[int(STATUS_FROM)])
                status_to_id = self.settings.get_status_to_id(default=int(STATUS_TO))

                # pobierz zamówienia dla wielu statusów
                all_orders: List[Dict[str, Any]] = []
                for sid in status_from_ids:
                    try:
                        all_orders.extend(self.apilo.get_orders_in_status(int(sid)))
                    except Exception as e:
                        print(f"[WARN] Nie udało się pobrać zamówień dla statusu {sid}: {e}")

                # uniq po order_id
                uniq: Dict[str, Dict[str, Any]] = {}
                for o in all_orders:
                    oid = o.get("id") or o.get("orderId")
                    if oid:
                        uniq[str(oid)] = o

                orders = list(uniq.values())
                print(
                    f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] znaleziono {len(orders)} zamówień "
                    f"(statusy: {status_from_ids} -> {status_to_id})"
                )

                for o in orders:
                    order_id = o.get("id") or o.get("orderId")
                    if not order_id:
                        continue
                    order_id = str(order_id)

                    # blokada na poziomie zamówienia
                    if done.get(order_id) in ("processing", "done"):
                        continue

                    details = self.apilo.get_order_details(order_id)

                    email = extract_customer_email(details)
                    phone = extract_customer_phone(details)
                    payment_id = extract_payment_id(details)
                    order_skus = extract_skus(details)

                    invoice_url = ""
                    try:
                        invoice_url = self.apilo.get_invoice_download_url(order_id) or ""
                    except Exception as e:
                        print(f"[WARN] Nie udało się pobrać faktury dla {order_id}: {e}")

                    fmt = {
                        "order_id": order_id,
                        "payment_id": payment_id,
                        "email": email or "",
                        "phone": phone or "",
                        "invoice_url": invoice_url,
                    }

                    done[order_id] = "processing"
                    self.processed.save(done)

                    sent_any_email = False
                    sent_any_sms = False

                    # =========================
                    # EMAIL
                    # =========================
                    if email:
                        email_to_send = self.templates.match_email_templates_for_skus(order_skus)
                        email_to_send.sort(
                            key=lambda t: (int(t.get("priority") or 100), str(t.get("updated_at") or ""))
                        )

                        for tpl in email_to_send:
                            tpl_id = int(tpl["id"])
                            tpl_key = tpl.get("template_key")

                            # DRY_RUN: nie używamy dedupe tabel, tylko logujemy
                            if not self.dry_run:
                                if self._was_email_sent(order_id, tpl_id):
                                    continue

                            subject = safe_format(tpl.get("subject", ""), fmt)
                            body = safe_format(tpl.get("body", ""), fmt)
                            is_html = bool(tpl.get("is_html", 0))

                            try:
                                if self.dry_run:
                                    print(f"[DRY_RUN] EMAIL order={order_id} tpl={tpl_key} -> {email}")
                                else:
                                    self.mailer.send(email, subject, body, is_html=is_html)

                                # KLUCZ: markuj jako wysłane dopiero po sukcesie
                                if not self.dry_run:
                                    self._mark_email_sent(order_id, tpl_id)

                                sent_any_email = True

                            except Exception as e:
                                print(f"[ERR] EMAIL send failed order={order_id} tpl={tpl_key}: {e}")
                                # nie markujemy - poleci ponownie w następnym cyklu
                                continue

                    # =========================
                    # SMS
                    # =========================
                    if self.sms_sender and phone:
                        sms_to_send = self.templates.match_sms_templates_for_skus(order_skus)
                        sms_to_send.sort(
                            key=lambda t: (int(t.get("priority") or 100), str(t.get("updated_at") or ""))
                        )

                        for tpl in sms_to_send:
                            tpl_id = int(tpl["id"])
                            tpl_key = tpl.get("template_key")

                            if not self.dry_run:
                                if self._was_sms_sent(order_id, tpl_id):
                                    continue

                            msg = safe_format(tpl.get("body", ""), fmt)

                            try:
                                if self.dry_run:
                                    print(f"[DRY_RUN] SMS order={order_id} tpl={tpl_key} -> {phone}: {msg}")
                                else:
                                    self.sms_sender.send_sms(phone, msg)

                                # KLUCZ: markuj jako wysłane dopiero po sukcesie
                                if not self.dry_run:
                                    self._mark_sms_sent(order_id, tpl_id)

                                sent_any_sms = True

                            except Exception as e:
                                print(f"[ERR] SMS send failed order={order_id} tpl={tpl_key}: {e}")
                                # nie markujemy - poleci ponownie w następnym cyklu
                                continue

                    # status_to_id == 0 => nie zmieniaj statusu
                    if (sent_any_email or sent_any_sms) and (not self.dry_run) and int(status_to_id) != 0:
                        try:
                            self.apilo.update_order_status(order_id, int(status_to_id))
                        except Exception as e:
                            print(f"[ERR] Status update failed order={order_id} -> {status_to_id}: {e}")
                            # tu zostawiamy done=done (żeby nie spamować mailami)
                            # jeśli chcesz, można zmienić logikę - ale to ryzykowne

                    done[order_id] = "done"
                    self.processed.save(done)

            except Exception as e:
                print(f"[ERR] {e}")

            time.sleep(self.poll_seconds)
