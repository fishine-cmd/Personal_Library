import json
from datetime import date, datetime, timedelta, timezone

import requests

from ..extensions import db
from ..models import AIAgentActivity, AIAgentJournal, AIAgentSetting

DEFAULT_AGENT_NAME = "小咪"
DEFAULT_POSITION_X = 24
DEFAULT_POSITION_Y = 24


class AIAgentError(Exception):
    """Raised when the configured AI agent service cannot generate a journal."""


def _local_period_start(period: str) -> datetime:
    now = datetime.now().astimezone()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "week":
        start -= timedelta(days=start.weekday())
    return start.astimezone(timezone.utc)


def journal_date_range(period: str) -> tuple[date, date]:
    now = datetime.now().astimezone()
    local_today = now.date()
    if period == "today":
        return local_today, local_today
    if period == "week":
        week_start = local_today - timedelta(days=local_today.weekday())
        return week_start, week_start + timedelta(days=6)
    raise ValueError("period must be 'today' or 'week'")


def get_or_create_setting(user_id: int, commit: bool = True) -> AIAgentSetting:
    setting = db.session.get(AIAgentSetting, user_id)
    if setting is None:
        setting = AIAgentSetting(
            user_id=user_id,
            agent_name=DEFAULT_AGENT_NAME,
            enabled=True,
            facing="right",
            position_x=DEFAULT_POSITION_X,
            position_y=DEFAULT_POSITION_Y,
        )
        db.session.add(setting)
        if commit:
            db.session.commit()
        else:
            db.session.flush()
    elif setting.migrate_api_key_to_encrypted():
        if commit:
            db.session.commit()
        else:
            db.session.flush()
    return setting


def serialize_setting(setting: AIAgentSetting) -> dict:
    return {
        "agent_name": setting.agent_name or DEFAULT_AGENT_NAME,
        "enabled": bool(setting.enabled),
        "facing": setting.facing if setting.facing in {"left", "right"} else "right",
        "position_x": int(setting.position_x or DEFAULT_POSITION_X),
        "position_y": int(setting.position_y or DEFAULT_POSITION_Y),
        "api_url": setting.api_url or "",
        "api_key_configured": bool(setting.api_key),
        "model": setting.model or "",
    }


def sanitize_metadata(metadata) -> dict:
    if not isinstance(metadata, dict):
        return {}
    safe = {}
    for key, value in metadata.items():
        if key in {"password", "api_key", "token", "secret"}:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[str(key)[:64]] = value
        else:
            safe[str(key)[:64]] = str(value)[:500]
    return safe


def record_activity(
    user_id: int,
    event_type: str,
    label: str,
    metadata: dict | None = None,
    *,
    commit: bool = True,
    silent: bool = True,
) -> AIAgentActivity | None:
    event_type = (event_type or "activity").strip()[:64] or "activity"
    label = (label or event_type).strip()[:256] or event_type
    metadata_json = json.dumps(
        sanitize_metadata(metadata), ensure_ascii=False, default=str
    )[:5000]
    activity = AIAgentActivity(
        user_id=user_id,
        event_type=event_type,
        label=label,
        metadata_json=metadata_json,
    )
    try:
        db.session.add(activity)
        if commit:
            db.session.commit()
        else:
            db.session.flush()
        return activity
    except Exception:
        db.session.rollback()
        if silent:
            return None
        raise


def activities_for_period(user_id: int, period: str) -> list[AIAgentActivity]:
    if period not in {"today", "week"}:
        raise ValueError("period must be 'today' or 'week'")
    start = _local_period_start(period)
    return (
        AIAgentActivity.query.filter(
            AIAgentActivity.user_id == user_id,
            AIAgentActivity.created_at >= start,
        )
        .order_by(AIAgentActivity.created_at.asc())
        .limit(500)
        .all()
    )


def _journal_title(period: str, start_date: date, end_date: date) -> str:
    if period == "daily":
        return f"{start_date.isoformat()} 日志"
    return f"{start_date.isoformat()} ~ {end_date.isoformat()} 周札"


def save_generated_journal(
    user_id: int,
    period: str,
    content: str,
    *,
    commit: bool = True,
) -> AIAgentJournal:
    if period not in {"daily", "weekly"}:
        raise ValueError("period must be 'daily' or 'weekly'")
    start_date, end_date = journal_date_range("today" if period == "daily" else "week")
    title = _journal_title(period, start_date, end_date)
    journal = (
        AIAgentJournal.query.filter_by(
            user_id=user_id, period=period, start_date=start_date
        ).first()
    )
    if journal is None:
        journal = AIAgentJournal(
            user_id=user_id,
            period=period,
            start_date=start_date,
            end_date=end_date,
            title=title,
            content=content,
        )
        db.session.add(journal)
    else:
        journal.end_date = end_date
        journal.title = title
        journal.content = content
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return journal


def list_month_daily_journals(user_id: int, year: int, month: int) -> list[AIAgentJournal]:
    month_start = date(year, month, 1)
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    return (
        AIAgentJournal.query.filter(
            AIAgentJournal.user_id == user_id,
            AIAgentJournal.period == "daily",
            AIAgentJournal.start_date >= month_start,
            AIAgentJournal.start_date < next_month,
        )
        .order_by(AIAgentJournal.start_date.asc())
        .all()
    )


def list_month_weekly_journals(user_id: int, range_start: date, range_end: date) -> list[AIAgentJournal]:
    return (
        AIAgentJournal.query.filter(
            AIAgentJournal.user_id == user_id,
            AIAgentJournal.period == "weekly",
            AIAgentJournal.start_date <= range_end,
            AIAgentJournal.end_date >= range_start,
        )
        .order_by(AIAgentJournal.start_date.asc())
        .all()
    )


def activity_to_dict(activity: AIAgentActivity) -> dict:
    try:
        metadata = json.loads(activity.metadata_json or "{}")
    except json.JSONDecodeError:
        metadata = {}
    created_at = activity.created_at
    if created_at and created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return {
        "time": created_at.isoformat() if created_at else "",
        "event_type": activity.event_type,
        "label": activity.label,
        "metadata": metadata,
    }


def build_activity_summary(activities: list[AIAgentActivity]) -> str:
    if not activities:
        return "暂无记录到的使用活动。"
    lines = []
    for activity in activities:
        created_at = activity.created_at
        if created_at and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        time_label = created_at.astimezone().strftime("%Y-%m-%d %H:%M") if created_at else ""
        lines.append(f"- {time_label} [{activity.event_type}] {activity.label}")
    return "\n".join(lines)


def _extract_content(response_payload) -> str:
    if isinstance(response_payload, str):
        return response_payload.strip()
    if not isinstance(response_payload, dict):
        return json.dumps(response_payload, ensure_ascii=False)

    for key in ("content", "text", "result", "message"):
        value = response_payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            nested = value.get("content") or value.get("text")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()

    choices = response_payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return message["content"].strip()
            if isinstance(first.get("text"), str):
                return first["text"].strip()

    return json.dumps(response_payload, ensure_ascii=False)


def _build_messages(
    setting: AIAgentSetting,
    period: str,
    activities: list[AIAgentActivity],
) -> list[dict]:
    agent_name = setting.agent_name or DEFAULT_AGENT_NAME
    period_label = "今日" if period == "today" else "本周（周札）"
    system_prompt = (
        f"你是用户在 Personal Library 文献管理系统里的桌面伙伴，名字叫{agent_name}，"
        "是一只温柔、聪明、爱用「喵」「呐」语气的猫娘。"
        "请用第一人称从猫娘视角写日志，要求："
        "1) 简洁自然有条理，分要点列出用户做了什么；"
        "2) 语气可爱但不油腻，可适当用「喵」「呐」收尾；"
        "3) 可适当加入可爱的颜文字；"
        "4) 使用 Markdown 格式；"
        "5) 结尾给一句简短鼓励。"
    )
    user_prompt = (
        f"以下是用户{period_label}（{period}）在 Personal Library 的活动记录，"
        "请据此生成一份中文日志：\n\n"
        f"{build_activity_summary(activities)}"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def generate_journal(
    setting: AIAgentSetting,
    period: str,
    activities: list[AIAgentActivity],
    *,
    timeout: float = 30.0,
) -> str:
    api_url = (setting.api_url or "").strip()
    if not api_url:
        raise AIAgentError("请先在设置页填写 AI Agent 接入 URL")

    model = (setting.model or "").strip()
    if not model:
        raise AIAgentError("请先在设置页填写 AI 模型名称（如 deepseek-chat）")

    payload = {
        "model": model,
        "messages": _build_messages(setting, period, activities),
        "stream": False,
    }
    headers = {"Content-Type": "application/json"}
    api_key = (setting.api_key or "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        response = requests.post(api_url, json=payload, headers=headers, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise AIAgentError(f"AI Agent 请求失败: {exc}") from exc

    try:
        body = response.json()
    except ValueError:
        body = response.text

    content = _extract_content(body)
    if not content:
        raise AIAgentError("AI Agent 返回为空")
    return content
