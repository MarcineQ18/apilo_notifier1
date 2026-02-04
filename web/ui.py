from flask import Blueprint, render_template, request, redirect, url_for, flash

from web.auth import auth
from web.templates_repo import TemplatesRepo
from web.settings_repo import SettingsRepo
from apilo_client import ApiloClient


def _parse_skus(raw: str) -> list[str]:
    if not raw:
        return []
    return [x.strip() for x in raw.replace(",", "\n").splitlines() if x.strip()]


def create_ui_blueprint(repo: TemplatesRepo, settings: SettingsRepo, apilo: ApiloClient) -> Blueprint:
    bp = Blueprint("ui", __name__)

    @bp.get("/")
    @auth
    def home():
        return redirect(url_for("ui.templates_list"))

    # =========================
    # SETTINGS
    # =========================
    @bp.get("/settings")
    @auth
    def app_settings():
        statuses = apilo.get_status_map()
        status_map = {
            int(s.get("id")): (s.get("name") or f"ID {s.get('id')}")
            for s in statuses
            if s.get("id") is not None
        }

        from settings import STATUS_FROM, STATUS_TO

        selected_from = settings.get_status_from_ids(default=[int(STATUS_FROM)])
        selected_to = settings.get_status_to_id(default=int(STATUS_TO))

        statuses_sorted = sorted(
            [{"id": int(k), "name": v} for k, v in status_map.items()],
            key=lambda x: x["name"].lower()
        )

        return render_template(
            "settings.html",
            statuses=statuses_sorted,
            selected_from=set(selected_from),
            selected_to=int(selected_to),
        )

    @bp.post("/settings")
    @auth
    def app_settings_post():
        from_ids_raw = request.form.getlist("status_from_ids")
        to_id_raw = request.form.get("status_to_id")  # może być "0" = nie zmieniaj

        try:
            from_ids = [int(x) for x in from_ids_raw]
            to_id = int(to_id_raw) if to_id_raw is not None else 0
        except Exception:
            flash("Błędne wartości statusów", "err")
            return redirect(url_for("ui.app_settings"))

        if not from_ids:
            flash("Wybierz co najmniej jeden status wejściowy", "err")
            return redirect(url_for("ui.app_settings"))

        settings.set_status_from_ids(from_ids)
        settings.set_status_to_id(to_id)

        flash("Zapisano ustawienia statusów pollera", "ok")
        return redirect(url_for("ui.app_settings"))

    # =========================
    # EMAIL TEMPLATES
    # =========================
    @bp.get("/templates")
    @auth
    def templates_list():
        items = repo.list_templates_with_skus()
        return render_template("templates_list.html", items=items)

    @bp.get("/templates/new")
    @auth
    def templates_new():
        return render_template("template_edit.html", item=None)

    @bp.post("/templates/new")
    @auth
    def templates_new_post():
        template_key = request.form["template_key"].strip()
        name = request.form["name"].strip()
        subject = request.form.get("subject", "").strip()
        body = request.form.get("body", "")
        is_html = 1 if request.form.get("is_html") in ("1", "on", "true", "yes") else 0
        priority = int(request.form.get("priority") or 100)
        is_active = 1 if request.form.get("is_active") in ("1", "on", "true", "yes") else 0

        repo.upsert(
            template_key=template_key,
            name=name,
            subject=subject,
            body=body,
            is_html=is_html,
            priority=priority,
            is_active=is_active,
        )

        tpl_id = None
        for t in repo.list_templates_with_skus():
            if str(t.get("template_key")) == template_key:
                tpl_id = int(t["id"])
                break

        if tpl_id is not None:
            skus = _parse_skus(request.form.get("skus", ""))
            repo.set_template_skus(tpl_id, skus)

        flash("Zapisano szablon email", "ok")
        return redirect(url_for("ui.templates_list"))

    @bp.get("/templates/<int:template_id>")
    @auth
    def templates_edit(template_id: int):
        item = repo.get_template(template_id)
        if not item:
            flash("Nie znaleziono szablonu email", "err")
            return redirect(url_for("ui.templates_list"))

        item["skus"] = "\n".join(item.get("skus") or [])
        item["is_active"] = int(item.get("is_active") or 0)
        return render_template("template_edit.html", item=item)

    @bp.post("/templates/<int:template_id>")
    @auth
    def templates_edit_post(template_id: int):
        item = repo.get_template(template_id)
        if not item:
            flash("Nie znaleziono szablonu email", "err")
            return redirect(url_for("ui.templates_list"))

        name = request.form["name"].strip()
        subject = request.form.get("subject", "").strip()
        body = request.form.get("body", "")
        is_html = 1 if request.form.get("is_html") in ("1", "on", "true", "yes") else 0
        priority = int(request.form.get("priority") or 100)
        is_active = 1 if request.form.get("is_active") in ("1", "on", "true", "yes") else 0

        repo.update_by_id(
            template_id=template_id,
            name=name,
            subject=subject,
            body=body,
            is_html=is_html,
            priority=priority,
            is_active=is_active,
        )

        skus = _parse_skus(request.form.get("skus", ""))
        repo.set_template_skus(template_id, skus)

        flash("Zapisano zmiany", "ok")
        return redirect(url_for("ui.templates_edit", template_id=template_id))

    @bp.post("/templates/<int:template_id>/delete")
    @auth
    def templates_delete(template_id: int):
        repo.delete_template(template_id)
        flash("Usunięto szablon email", "ok")
        return redirect(url_for("ui.templates_list"))

    # =========================
    # SMS TEMPLATES
    # =========================
    @bp.get("/sms-templates")
    @auth
    def sms_templates_list():
        items = repo.list_sms_templates_with_skus()
        return render_template("sms_templates_list.html", items=items)

    @bp.get("/sms-templates/new")
    @auth
    def sms_templates_new():
        return render_template("sms_template_edit.html", item=None)

    @bp.post("/sms-templates/new")
    @auth
    def sms_templates_new_post():
        template_key = request.form["template_key"].strip()
        name = request.form["name"].strip()
        body = request.form.get("body", "")
        priority = int(request.form.get("priority") or 100)
        is_active = 1 if request.form.get("is_active") in ("1", "on", "true", "yes") else 0

        repo.upsert_sms(template_key=template_key, name=name, body=body, priority=priority, is_active=is_active)

        tpl_id = None
        for t in repo.list_sms_templates_with_skus():
            if str(t.get("template_key")) == template_key:
                tpl_id = int(t["id"])
                break

        if tpl_id is not None:
            skus = _parse_skus(request.form.get("skus", ""))
            repo.set_sms_template_skus(tpl_id, skus)

        flash("Zapisano szablon SMS", "ok")
        return redirect(url_for("ui.sms_templates_list"))

    @bp.get("/sms-templates/<int:template_id>")
    @auth
    def sms_templates_edit(template_id: int):
        item = repo.get_sms_template(template_id)
        if not item:
            flash("Nie znaleziono szablonu SMS", "err")
            return redirect(url_for("ui.sms_templates_list"))

        item["skus"] = "\n".join(item.get("skus") or [])
        item["is_active"] = int(item.get("is_active") or 0)
        return render_template("sms_template_edit.html", item=item)

    @bp.post("/sms-templates/<int:template_id>")
    @auth
    def sms_templates_edit_post(template_id: int):
        item = repo.get_sms_template(template_id)
        if not item:
            flash("Nie znaleziono szablonu SMS", "err")
            return redirect(url_for("ui.sms_templates_list"))

        name = request.form["name"].strip()
        body = request.form.get("body", "")
        priority = int(request.form.get("priority") or 100)
        is_active = 1 if request.form.get("is_active") in ("1", "on", "true", "yes") else 0

        repo.update_sms_by_id(template_id=template_id, name=name, body=body, priority=priority, is_active=is_active)

        skus = _parse_skus(request.form.get("skus", ""))
        repo.set_sms_template_skus(template_id, skus)

        flash("Zapisano zmiany", "ok")
        return redirect(url_for("ui.sms_templates_edit", template_id=template_id))

    @bp.post("/sms-templates/<int:template_id>/delete")
    @auth
    def sms_templates_delete(template_id: int):
        repo.delete_sms_template(template_id)
        flash("Usunięto szablon SMS", "ok")
        return redirect(url_for("ui.sms_templates_list"))

    return bp
