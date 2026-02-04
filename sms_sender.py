import re
import time
import requests
from typing import Optional, Dict, Any, Tuple
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class SmsPlanetSender:
    def __init__(
        self,
        token: str,
        sender_name: str,
        api_base: str = "https://api2.smsplanet.pl",
        timeout: int = 20,
        test_mode: bool = False,
        max_attempts: int = 4,
        backoff_factor: float = 1.0,
        connect_timeout: int = 8,
    ):
        self.api_base = api_base.rstrip("/")
        self.token = (token or "").strip()
        self.sender_name = (sender_name or "").strip()

        # timeout = read timeout
        self.read_timeout = int(timeout)
        self.connect_timeout = int(connect_timeout)

        self.test_mode = bool(test_mode)
        self.max_attempts = int(max_attempts)
        self.backoff_factor = float(backoff_factor)

        if not self.token:
            raise ValueError("Brak SMSPLANET_TOKEN")
        if not self.sender_name:
            raise ValueError("Brak SMS_FROM")

        self.session = self._make_session()

    def _make_session(self) -> requests.Session:
        s = requests.Session()

        # Retry na poziomie urllib3 (działa dla transient HTTP i części wyjątków)
        retry = Retry(
            total=5,
            connect=5,
            read=5,
            status=5,
            backoff_factor=0.8,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("POST", "GET"),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)

        s.mount("https://", adapter)
        s.mount("http://", adapter)
        return s

    def _reset_session(self) -> None:
        try:
            self.session.close()
        except Exception:
            pass
        self.session = self._make_session()

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }

    @staticmethod
    def normalize_phone(phone: str) -> Optional[str]:
        if not phone:
            return None
        p = str(phone).strip()
        p = re.sub(r"[^\d+]", "", p)

        # PL
        if p.startswith("+48") and len(p) == 12:
            return p
        if p.startswith("48") and len(p) == 11:
            return "+" + p
        if re.fullmatch(r"\d{9}", p):
            return "+48" + p

        # International
        if p.startswith("+") and len(p) >= 10:
            return p
        if re.fullmatch(r"\d{10,15}", p):
            return "+" + p

        return None

    def _timeout(self) -> Tuple[int, int]:
        # (connect, read)
        return (self.connect_timeout, self.read_timeout)

    def send_sms(self, to_phone: str, message: str) -> str:
        to_norm = self.normalize_phone(to_phone)
        if not to_norm:
            raise ValueError(f"Niepoprawny numer telefonu: {to_phone}")

        url = f"{self.api_base}/sms"
        data = {
            "from": self.sender_name,
            "to": to_norm,
            "msg": message,
        }
        if self.test_mode:
            data["test"] = "1"

        last_err: Optional[Exception] = None

        # Retry "aplikacyjny" (poza urllib3), żeby:
        # - łapać wyjątki requests (timeout, connection reset)
        # - robić backoff
        # - resetować sesję po problemach
        for attempt in range(1, self.max_attempts + 1):
            try:
                r = self.session.post(
                    url,
                    headers=self._headers(),
                    data=data,
                    timeout=self._timeout(),
                )

                # jeśli serwer zwróci 5xx/429 - potraktuj jak transient
                if r.status_code in (429, 500, 502, 503, 504):
                    raise RuntimeError(f"SMSPLANET transient HTTP {r.status_code}: {r.text}")

                # parsing json
                try:
                    payload: Dict[str, Any] = r.json() if r.text else {}
                except Exception:
                    payload = {}

                if r.status_code != 200:
                    raise RuntimeError(f"SMSPLANET HTTP {r.status_code}: {r.text}")

                if isinstance(payload, dict):
                    if "messageId" in payload:
                        return str(payload["messageId"])
                    if "errorMsg" in payload:
                        raise RuntimeError(
                            f"SMSPLANET error {payload.get('errorCode')}: {payload.get('errorMsg')}"
                        )

                raise RuntimeError(f"SMSPLANET unknown response: {r.text}")

            except Exception as e:
                last_err = e

                # ostatnia próba => wywal błąd
                if attempt >= self.max_attempts:
                    break

                # po problemach sieciowych warto odświeżyć sesję
                self._reset_session()

                # backoff: 1s, 2s, 4s... (zależnie od backoff_factor)
                sleep_s = self.backoff_factor * (2 ** (attempt - 1))
                time.sleep(sleep_s)

        raise RuntimeError(f"SMSPLANET send failed after {self.max_attempts} attempts: {last_err}")
