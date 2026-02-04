import os
import threading
import time
from flask import Flask

from settings import (
    APILO_BASE,
    APILO_ACCESS_TOKEN,
    APILO_REFRESH_TOKEN,
    APILO_CLIENT_ID,
    APILO_CLIENT_SECRET,
    POLL_SECONDS,
    PAGE_LIMIT,
    REQUEST_TIMEOUT,
    DRY_RUN,
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASS,
    MAIL_FROM,
    WEB_HOST,
    WEB_PORT,
    SMSPLANET_TOKEN,
    SMS_FROM,
    SMS_TEST_MODE,
)

from db import init_db
from apilo_client import ApiloClient
from mailer import Mailer
from sms_sender import SmsPlanetSender
from processed_store import ProcessedStore
from poller import Poller
from web.templates_repo import TemplatesRepo
from web.settings_repo import SettingsRepo
from web.ui import create_ui_blueprint


def create_app() -> Flask:
    app = Flask(__name__, template_folder="web/jinja")
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret")

    # =========================
    # DB
    # =========================
    os.makedirs(app.instance_path, exist_ok=True)
    db_path = os.path.join(app.instance_path, "app.db")
    init_db(db_path)

    templates_repo = TemplatesRepo(db_path)
    settings_repo = SettingsRepo(db_path)

    # =========================
    # TOKEN CALLBACK
    # =========================
    def on_tokens_updated(
        new_access: str,
        new_refresh: str,
        access_exp: str, 
        refresh_exp: str,
    ) -> None:
        settings_repo.set_apilo_tokens(
            new_access,
            new_refresh,
            access_exp,
            refresh_exp,
        )

    # =========================
    # APILO
    # =========================
    apilo = ApiloClient(
        base_url=APILO_BASE,
        access_token=settings_repo.get_apilo_access_token() or APILO_ACCESS_TOKEN,
        refresh_token=settings_repo.get_apilo_refresh_token() or APILO_REFRESH_TOKEN,
        client_id=APILO_CLIENT_ID,
        client_secret=APILO_CLIENT_SECRET,
        token_updated_cb=on_tokens_updated,
        page_limit=PAGE_LIMIT,
        timeout=REQUEST_TIMEOUT,
    )

    # =========================
    # UI
    # =========================
    app.register_blueprint(
        create_ui_blueprint(templates_repo, settings_repo, apilo)
    )

    # =========================
    # MAIL
    # =========================
    mailer = Mailer(
        host=SMTP_HOST,
        port=SMTP_PORT,
        user=SMTP_USER,
        password=SMTP_PASS,
        mail_from=MAIL_FROM,
    )

    # =========================
    # SMS
    # =========================
    sms_sender = None
    if SMSPLANET_TOKEN and SMS_FROM:
        sms_sender = SmsPlanetSender(
            token=SMSPLANET_TOKEN,
            sender_name=SMS_FROM,
            test_mode=SMS_TEST_MODE,
        )

    # =========================
    # PROCESSED
    # =========================
    processed = ProcessedStore(
        os.path.join(app.instance_path, "processed.json")
    )

    poller = Poller(
        apilo=apilo,
        mailer=mailer,
        templates=templates_repo,
        processed=processed,
        poll_seconds=POLL_SECONDS,
        dry_run=DRY_RUN,
        db_path=db_path,
        sms_sender=sms_sender,
    )

    def poller_thread():
        time.sleep(1)
        poller.run_forever()

    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        threading.Thread(target=poller_thread, daemon=True).start()
        print("[OK] Poller thread started")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host=WEB_HOST, port=WEB_PORT, debug=True)