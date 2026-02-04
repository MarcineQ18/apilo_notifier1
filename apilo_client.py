import json
import time
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class ApiloClient:
    def __init__(
        self,
        base_url: str,
        access_token: str,
        refresh_token: Optional[str],
        client_id: Optional[str],
        client_secret: Optional[str],
        token_updated_cb=None,
        page_limit: int = 200,
        timeout: int = 120,
    ):
        self.base_url = (base_url or "").rstrip("/")
        self.access_token = (access_token or "").strip()
        self.refresh_token = (refresh_token or "").strip() if refresh_token else None
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_updated_cb = token_updated_cb

        self.page_limit = int(page_limit)
        self.timeout = int(timeout)
        self.session = self._make_session()

    # =========================
    # SESSION / HEADERS
    # =========================
    def _make_session(self) -> requests.Session:
        s = requests.Session()
        retries = Retry(
            total=5,
            backoff_factor=1.2,
            status_forcelist=(401, 429, 500, 502, 503, 504),
            allowed_methods=("GET", "PUT", "POST"),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retries)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        return s

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    # =========================
    # TOKEN REFRESH
    # =========================
    def _can_refresh(self) -> bool:
        return bool(self.refresh_token and self.client_id and self.client_secret)

    def refresh_access_token(self) -> None:
        if not self._can_refresh():
            raise RuntimeError(
                "Brak danych do refresh tokenu (client_id, client_secret, refresh_token)"
            )

        url = f"{self.base_url}/rest/auth/token/"
        payload = {
            "grantType": "refresh_token",
            "token": self.refresh_token,
        }

        r = self.session.post(
            url,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            auth=(self.client_id, self.client_secret),
            data=json.dumps(payload),
            timeout=self.timeout,
        )

        if r.status_code not in (200, 201):
            raise RuntimeError(f"REFRESH failed: {r.status_code} {r.text}")

        data = r.json() or {}

        new_access = (data.get("accessToken") or "").strip()
        new_refresh = (data.get("refreshToken") or "").strip()
        access_exp = data.get("accessTokenExpireAt")
        refresh_exp = data.get("refreshTokenExpireAt")

        if not new_access or not new_refresh:
            raise RuntimeError("REFRESH response bez tokenów")

        self.access_token = new_access
        self.refresh_token = new_refresh

        if self.token_updated_cb:
            self.token_updated_cb(
                new_access,
                new_refresh,
                access_exp,
                refresh_exp,
            )

        print("[OK] Apilo token odnowiony (auto-refresh)")

    # =========================
    # SAFE REQUEST
    # =========================
    def _request(self, method: str, url: str, **kwargs):
        r = self.session.request(
            method,
            url,
            headers=self._headers(),
            timeout=self.timeout,
            **kwargs,
        )

        if r.status_code == 401:
            self.refresh_access_token()
            r = self.session.request(
                method,
                url,
                headers=self._headers(),
                timeout=self.timeout,
                **kwargs,
            )

        return r

    # =========================
    # API
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

            r = self._request("GET", url, params=params)
            if r.status_code != 200:
                raise RuntimeError(f"GET orders failed: {r.status_code} {r.text}")

            data = r.json() or {}
            batch = data.get("orders") or data.get("data") or []
            orders.extend(batch)

            if not batch:
                break

            offset += len(batch)

        return orders

    def get_order_details(self, order_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/rest/api/orders/{order_id}/"
        r = self._request("GET", url)
        if r.status_code != 200:
            raise RuntimeError(f"GET order failed: {r.status_code} {r.text}")
        return r.json() or {}

    def update_order_status(self, order_id: str, new_status: int) -> None:
        url = f"{self.base_url}/rest/api/orders/{order_id}/status/"
        payload = {"status": int(new_status)}
        r = self._request("PUT", url, data=json.dumps(payload))
        if r.status_code not in (200, 204, 304):
            raise RuntimeError(f"PUT status failed: {r.status_code} {r.text}")