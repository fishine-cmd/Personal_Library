from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import UserSetting
from ..services import mineru_client
from ..services.ai_agent import get_or_create_setting, record_activity

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
    agent = get_or_create_setting(current_user.id)
    if request.method == "POST":
        if request.form.get("form_name") == "ai_agent":
            agent.agent_name = (request.form.get("agent_name") or "").strip()[:64] or "小咪"
            agent.enabled = bool(request.form.get("agent_enabled"))
            agent.api_url = (request.form.get("ai_api_url") or "").strip() or None
            agent.model = (request.form.get("ai_model") or "").strip()[:64] or None
            if request.form.get("clear_ai_api_key"):
                agent.api_key = None
            else:
                api_key = (request.form.get("ai_api_key") or "").strip()
                if api_key:
                    agent.api_key = api_key
            db.session.commit()
            record_activity(current_user.id, "settings_save", "保存 AI Agent 设置")
            flash("AI Agent 设置已保存", "success")
        else:
            s.mineru_url = (request.form.get("mineru_url") or "").strip() or DEFAULT_MINERU_URL
            db.session.commit()
            record_activity(current_user.id, "settings_save", "保存 MinerU 设置")
            flash("设置已保存", "success")
        return redirect(url_for("settings.index"))
    return render_template(
        "settings/index.html",
        settings=s,
        agent=agent,
        default_url=DEFAULT_MINERU_URL,
    )


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
