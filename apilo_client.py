import json
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class ApiloClient:
    def __init__(self, base_url: str, token: str, page_limit: int = 200, timeout: int = 120):
        self.base_url = (base_url or "").rstrip("/")
        self.token = token
        self.page_limit = int(page_limit)
        self.timeout = int(timeout)
        self.session = self._make_session()

    def _make_session(self) -> requests.Session:
        s = requests.Session()
        retries = Retry(
            total=6,
            backoff_factor=1.2,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET", "PUT", "POST"),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=10)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        return s

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    # =========================
    # STATUS MAP (do UI /settings)
    # =========================
    def get_status_map(self) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/rest/api/orders/status/map/"
        r = self.session.get(url, headers=self._headers(), timeout=self.timeout)
        if r.status_code != 200:
            raise RuntimeError(f"GET status map failed: {r.status_code} {r.text}")
        return r.json() or []

    # =========================
    # ORDERS
    # =========================
    def get_orders_in_status(self, status_id: int) -> List[Dict[str, Any]]:
        orders: List[Dict[str, Any]] = []
        offset = 0

        while True:
            url = f"{self.base_url}/rest/api/orders/"
            params = {
                "orderStatusIds[]": int(status_id),
                "limit": self.page_limit,
                "offset": offset,
                "sort": "updatedAtDesc",
            }
            r = self.session.get(url, headers=self._headers(), params=params, timeout=self.timeout)
            if r.status_code != 200:
                raise RuntimeError(f"GET orders failed: {r.status_code} {r.text}")

            data = r.json() or {}
            batch = data.get("orders") or data.get("data") or data.get("results") or []
            orders.extend(batch)

            page_count = data.get("pageResultCount")
            total = data.get("totalCount")

            if page_count is None:
                if not batch:
                    break
                offset += len(batch)
                continue

            if page_count == 0:
                break

            offset += int(page_count)
            if total is not None and offset >= int(total):
                break

            if int(page_count) < self.page_limit:
                break

        return orders

    def get_order_details(self, order_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/rest/api/orders/{order_id}/"
        r = self.session.get(url, headers=self._headers(), timeout=self.timeout)
        if r.status_code != 200:
            raise RuntimeError(f"GET order details failed for {order_id}: {r.status_code} {r.text}")
        return r.json() or {}

    def update_order_status(self, order_id: str, new_status: int) -> None:
        url = f"{self.base_url}/rest/api/orders/{order_id}/status/"
        payload = {"status": int(new_status)}
        r = self.session.put(url, headers=self._headers(), data=json.dumps(payload), timeout=self.timeout)
        if r.status_code not in (200, 204, 304):
            raise RuntimeError(f"PUT status failed for {order_id}: {r.status_code} {r.text}")

    # =========================
    # DOCUMENTS / INVOICE
    # =========================
    def get_order_documents(self, order_id: str) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/rest/api/orders/{order_id}/documents/"
        r = self.session.get(url, headers=self._headers(), timeout=self.timeout)
        if r.status_code != 200:
            raise RuntimeError(f"GET documents failed for {order_id}: {r.status_code} {r.text}")
        data = r.json() or {}
        return data.get("documents") or data.get("data") or data.get("results") or data or []

    def get_document_details(self, order_id: str, doc_id: int) -> Dict[str, Any]:
        url = f"{self.base_url}/rest/api/orders/{order_id}/documents/{int(doc_id)}/"
        r = self.session.get(url, headers=self._headers(), timeout=self.timeout)
        if r.status_code != 200:
            raise RuntimeError(f"GET document details failed: {r.status_code} {r.text}")
        return r.json() or {}

    def get_invoice_download_url(self, order_id: str) -> Optional[str]:
        """
        Poprawny link wg Twojego przykładu:
        https://kudda.apilo.com/client/invoice-document/detail/<DOC_ID>/<MEDIA>/

        Zakładamy:
        - /documents/ ma 1 pozycję (u Ciebie tak jest)
        - szczegóły dokumentu mają pole "media"
        """
        docs = self.get_order_documents(order_id)
        if not docs:
            return None

        first = docs[0] or {}
        doc_id = first.get("id") or first.get("documentId")
        if not doc_id:
            return None

        det = self.get_document_details(order_id, int(doc_id))
        media = det.get("media")
        if not media:
            return None

        media = str(media).strip().strip("/")
        return f"{self.base_url}/client/invoice-document/detail/{int(doc_id)}/{media}/"

    # alias na wypadek różnych nazw w pollerze
    def get_invoice_url(self, order_id: str) -> Optional[str]:
        return self.get_invoice_download_url(order_id)
