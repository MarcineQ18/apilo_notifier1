import os
import threading
import time
from flask import Flask

from settings import (
    APILO_BASE, APILO_TOKEN,
    POLL_SECONDS, PAGE_LIMIT, REQUEST_TIMEOUT, DRY_RUN,
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, MAIL_FROM,
    WEB_HOST, WEB_PORT,
    SMSPLANET_TOKEN, SMS_FROM, SMS_TEST_MODE,
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
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key")

    # DB
    os.makedirs(app.instance_path, exist_ok=True)
    db_path = os.path.join(app.instance_path, "app.db")
    init_db(db_path)

    # Repos
    repo = TemplatesRepo(db_path)
    settings_repo = SettingsRepo(db_path)

    # Apilo client (UI też go używa do mapy statusów)
    apilo = ApiloClient(
        base_url=APILO_BASE,
        token=APILO_TOKEN,
        page_limit=PAGE_LIMIT,
        timeout=REQUEST_TIMEOUT,
    )

    # UI
    app.register_blueprint(create_ui_blueprint(repo, settings_repo, apilo))

    # Mailer
    mailer = Mailer(
        host=SMTP_HOST,
        port=SMTP_PORT,
        user=SMTP_USER,
        password=SMTP_PASS,
        mail_from=MAIL_FROM,
    )

    # SMS sender
    sms_sender = None
    if SMSPLANET_TOKEN and SMS_FROM:
        try:
            sms_sender = SmsPlanetSender(
                token=SMSPLANET_TOKEN,
                sender_name=SMS_FROM,
                test_mode=bool(SMS_TEST_MODE),
            )
            print("[OK] SMSPLANET sender zainicjalizowany")
        except Exception as e:
            print(f"[WARN] SMSPLANET init failed: {e}")

    # Processed store
    processed_path = os.path.join(app.instance_path, "processed.json")
    processed = ProcessedStore(processed_path)

    # Poller (statusy bierze z DB /settings)
    poller = Poller(
        apilo=apilo,
        mailer=mailer,
        templates=repo,
        processed=processed,
        poll_seconds=POLL_SECONDS,
        dry_run=DRY_RUN,
        db_path=db_path,
        sms_sender=sms_sender,
    )

    def poller_thread():
        time.sleep(1)
        poller.run_forever()

    # Debug reloader odpala 2 procesy:
    # - parent: WERKZEUG_RUN_MAIN brak
    # - child:  WERKZEUG_RUN_MAIN="true"
    # Poller odpalamy TYLKO w child.
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        threading.Thread(target=poller_thread, daemon=True).start()
        print("[OK] Poller thread started")
    else:
        print("[INFO] Pomijam pollera w parent reloadera")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host=WEB_HOST, port=WEB_PORT, debug=True)
