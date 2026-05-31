from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from ..extensions import db
from ..services.ai_agent import (
    AIAgentError,
    activities_for_period,
    generate_journal,
    get_or_create_setting,
    save_generated_journal,
    record_activity,
    serialize_setting,
)

bp = Blueprint("ai_agent", __name__)


def _clamp_float(value, low: float, high: float, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return min(max(number, low), high)


def _clamp_int(value, low: int, high: int, default: int) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return default
    return min(max(number, low), high)


@bp.route("/api/state", methods=["GET", "POST"])
@login_required
def api_state():
    setting = get_or_create_setting(current_user.id)
    if request.method == "GET":
        return jsonify(ok=True, state=serialize_setting(setting))

    payload = request.get_json(silent=True) or {}
    if "agent_name" in payload:
        name = (payload.get("agent_name") or "").strip()
        setting.agent_name = name[:64] or setting.agent_name or "小咪"
    if "enabled" in payload:
        setting.enabled = bool(payload.get("enabled"))
    if "scale" in payload:
        setting.scale = _clamp_float(payload.get("scale"), 0.5, 1.6, setting.scale or 1.0)
    if "facing" in payload:
        setting.facing = "left" if payload.get("facing") == "left" else "right"
    if "position_x" in payload:
        setting.position_x = _clamp_int(payload.get("position_x"), 0, 10000, setting.position_x or 24)
    if "position_y" in payload:
        setting.position_y = _clamp_int(payload.get("position_y"), 0, 10000, setting.position_y or 24)

    db.session.commit()
    record_activity(
        current_user.id,
        "agent_state_update",
        "更新 AI Agent 状态",
        {"fields": sorted(payload.keys())},
    )
    return jsonify(ok=True, state=serialize_setting(setting))


@bp.route("/api/activity", methods=["POST"])
@login_required
def api_activity():
    payload = request.get_json(silent=True) or {}
    record_activity(
        current_user.id,
        payload.get("event_type") or "activity",
        payload.get("label") or "用户活动",
        payload.get("metadata") or {},
        silent=False,
    )
    return jsonify(ok=True)


def _journal_response(period: str):
    setting = get_or_create_setting(current_user.id)
    activities = activities_for_period(current_user.id, period)
    try:
        content = generate_journal(setting, period, activities)
    except AIAgentError as exc:
        return jsonify(ok=False, error=str(exc)), 502

    journal = save_generated_journal(
        current_user.id,
        "daily" if period == "today" else "weekly",
        content,
    )

    record_activity(
        current_user.id,
        "journal_generate",
        "生成日志" if period == "today" else "生成周札",
        {"period": period, "activity_count": len(activities)},
    )
    return jsonify(
        ok=True,
        period=period,
        content=content,
        activity_count=len(activities),
        journal={
            "id": journal.id,
            "title": journal.title,
            "start_date": journal.start_date.isoformat(),
            "end_date": journal.end_date.isoformat(),
        },
    )


@bp.route("/api/journal/today", methods=["POST"])
@login_required
def journal_today():
    return _journal_response("today")


@bp.route("/api/journal/week", methods=["POST"])
@login_required
def journal_week():
    return _journal_response("week")
