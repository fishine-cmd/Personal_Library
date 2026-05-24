from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user

from ..extensions import db
from ..models import UserSetting
from ..services import mineru_client

bp = Blueprint("settings", __name__)

DEFAULT_MINERU_URL = "http://127.0.0.1:8000"


def _get_or_create_settings() -> UserSetting:
    s = db.session.get(UserSetting, current_user.id)
    if s is None:
        s = UserSetting(user_id=current_user.id, mineru_url=DEFAULT_MINERU_URL)
        db.session.add(s)
        db.session.commit()
    return s


@bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    s = _get_or_create_settings()
    if request.method == "POST":
        s.mineru_url = (request.form.get("mineru_url") or "").strip() or DEFAULT_MINERU_URL
        db.session.commit()
        flash("设置已保存", "success")
        return redirect(url_for("settings.index"))
    return render_template("settings/index.html", settings=s, default_url=DEFAULT_MINERU_URL)


@bp.route("/test_mineru", methods=["POST"])
@login_required
def test_mineru():
    url = (request.form.get("mineru_url") or "").strip()
    if not url:
        return jsonify(ok=False, error="请填写 MinerU 地址")
    try:
        info = mineru_client.health_check(url, timeout=4.0)
        return jsonify(
            ok=True,
            version=info.get("version"),
            status=info.get("status"),
            queued=info.get("queued_tasks"),
        )
    except mineru_client.MineruError as e:
        return jsonify(ok=False, error=str(e))
