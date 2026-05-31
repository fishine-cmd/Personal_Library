from datetime import datetime

from app.extensions import db
from app.models import AIAgentActivity, AIAgentJournal, AIAgentSetting, User
from app.services.ai_agent import get_or_create_setting, record_activity


def test_ai_agent_setting_and_activity_are_user_scoped(app):
    with app.app_context():
        u1 = User(username="agent_a")
        u1.set_password("pw123456")
        u2 = User(username="agent_b")
        u2.set_password("pw123456")
        db.session.add_all([u1, u2])
        db.session.commit()

        s1 = get_or_create_setting(u1.id)
        s2 = get_or_create_setting(u2.id)
        s1.agent_name = "Agent A"
        s2.agent_name = "Agent B"
        db.session.commit()

        record_activity(u1.id, "document_create", "Create A")
        record_activity(u2.id, "document_create", "Create B")

        assert db.session.get(AIAgentSetting, u1.id).agent_name == "Agent A"
        assert db.session.get(AIAgentSetting, u2.id).agent_name == "Agent B"
        assert AIAgentActivity.query.filter_by(user_id=u1.id).count() == 1
        assert AIAgentActivity.query.filter_by(user_id=u2.id).count() == 1


def test_ai_agent_state_requires_login(client):
    resp = client.get("/ai-agent/api/state")
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


def test_ai_agent_state_update_is_user_scoped(client):
    client.post(
        "/auth/register",
        data={"username": "alpha", "password": "pw123456", "password2": "pw123456"},
    )
    resp = client.post(
        "/ai-agent/api/state",
        json={
            "agent_name": "Alpha",
            "scale": 1.35,
            "facing": "left",
            "position_x": 120,
            "position_y": 80,
        },
    )
    assert resp.status_code == 200
    assert resp.get_json()["state"]["agent_name"] == "Alpha"

    client.get("/auth/logout")
    client.post(
        "/auth/register",
        data={"username": "beta", "password": "pw123456", "password2": "pw123456"},
    )
    resp = client.get("/ai-agent/api/state")
    assert resp.status_code == 200
    assert resp.get_json()["state"]["agent_name"] != "Alpha"


def test_settings_save_ai_agent_config_without_key_echo(login_client, app):
    resp = login_client.post(
        "/settings/",
        data={
            "form_name": "ai_agent",
            "agent_name": "Logger",
            "agent_enabled": "on",
            "ai_api_url": "https://ai.example.test/journal",
            "ai_api_key": "sk-secret-value",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"sk-secret-value" not in resp.data

    with app.app_context():
        setting = AIAgentSetting.query.one()
        assert setting.agent_name == "Logger"
        assert setting.api_url == "https://ai.example.test/journal"
        assert setting.api_key == "sk-secret-value"


def _patch_post(monkeypatch, response_body):
    calls = []

    class FakeResponse:
        text = ""

        def raise_for_status(self):
            return None

        def json(self):
            return response_body

    def fake_post(url, json, headers, timeout):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return FakeResponse()

    from app.services import ai_agent as ai_agent_service

    monkeypatch.setattr(ai_agent_service.requests, "post", fake_post)
    return calls


def test_journal_generation_calls_openai_chat_completions(login_client, app, monkeypatch):
    with app.app_context():
        user = User.query.filter_by(username="tester").first()
        setting = get_or_create_setting(user.id)
        setting.api_url = "https://api.deepseek.com/v1/chat/completions"
        setting.api_key = "sk-test"
        setting.model = "deepseek-chat"
        db.session.commit()
        record_activity(setting.user_id, "document_create", "import doc A")

    calls = _patch_post(
        monkeypatch,
        {"choices": [{"message": {"role": "assistant", "content": "journal content"}}]},
    )

    resp = login_client.post("/ai-agent/api/journal/today")
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data["ok"] is True
    assert "journal content" in data["content"]

    with app.app_context():
        journal = AIAgentJournal.query.filter_by(period="daily").first()
        assert journal is not None
        assert journal.content == "journal content"

    sent = calls[0]
    assert sent["url"] == "https://api.deepseek.com/v1/chat/completions"
    assert sent["headers"]["Authorization"] == "Bearer sk-test"
    body = sent["json"]
    assert body["model"] == "deepseek-chat"
    messages = body["messages"]
    assert isinstance(messages, list) and len(messages) >= 2
    assert messages[0]["role"] == "system"
    assert messages[-1]["role"] == "user"
    assert "import doc A" in messages[-1]["content"]


def test_journal_generation_errors_when_model_missing(login_client, app, monkeypatch):
    with app.app_context():
        user = User.query.filter_by(username="tester").first()
        setting = get_or_create_setting(user.id)
        setting.api_url = "https://api.deepseek.com/v1/chat/completions"
        setting.api_key = "sk-test"
        setting.model = None
        db.session.commit()

    _patch_post(monkeypatch, {"choices": []})

    resp = login_client.post("/ai-agent/api/journal/today")
    assert resp.status_code == 502
    data = resp.get_json()
    assert data["ok"] is False
    assert "模型" in data["error"]


def test_settings_save_ai_agent_model_field(login_client, app):
    resp = login_client.post(
        "/settings/",
        data={
            "form_name": "ai_agent",
            "agent_name": "assistant",
            "agent_enabled": "on",
            "ai_api_url": "https://api.deepseek.com/v1/chat/completions",
            "ai_api_key": "sk-secret",
            "ai_model": "deepseek-chat",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        setting = AIAgentSetting.query.one()
        assert setting.model == "deepseek-chat"


def test_week_journal_generation_is_upserted(login_client, app, monkeypatch):
    with app.app_context():
        user = User.query.filter_by(username="tester").first()
        setting = get_or_create_setting(user.id)
        setting.api_url = "https://api.deepseek.com/v1/chat/completions"
        setting.api_key = "sk-test"
        setting.model = "deepseek-chat"
        db.session.commit()

    _patch_post(monkeypatch, {"choices": [{"message": {"content": "first"}}]})
    first = login_client.post("/ai-agent/api/journal/week")
    assert first.status_code == 200

    _patch_post(monkeypatch, {"choices": [{"message": {"content": "second"}}]})
    second = login_client.post("/ai-agent/api/journal/week")
    assert second.status_code == 200

    with app.app_context():
        journals = AIAgentJournal.query.filter_by(period="weekly").all()
        assert len(journals) == 1
        assert journals[0].content == "second"


def test_daily_journal_generation_is_upserted(login_client, app, monkeypatch):
    with app.app_context():
        user = User.query.filter_by(username="tester").first()
        setting = get_or_create_setting(user.id)
        setting.api_url = "https://api.deepseek.com/v1/chat/completions"
        setting.api_key = "sk-test"
        setting.model = "deepseek-chat"
        db.session.commit()

    _patch_post(monkeypatch, {"choices": [{"message": {"content": "daily first"}}]})
    first = login_client.post("/ai-agent/api/journal/today")
    assert first.status_code == 200

    _patch_post(monkeypatch, {"choices": [{"message": {"content": "daily second"}}]})
    second = login_client.post("/ai-agent/api/journal/today")
    assert second.status_code == 200

    with app.app_context():
        journals = AIAgentJournal.query.filter_by(period="daily").all()
        assert len(journals) == 1
        assert journals[0].content == "daily second"


def test_journal_page_renders_calendar(login_client, app):
    with app.app_context():
        user = User.query.filter_by(username="tester").first()
        today = datetime.now().date()
        db.session.add(
            AIAgentJournal(
                user_id=user.id,
                period="daily",
                start_date=today,
                end_date=today,
                title=f"{today.isoformat()} journal",
                content="today journal",
            )
        )
        db.session.commit()

    resp = login_client.get("/journals/")
    assert resp.status_code == 200
    assert b"today journal" in resp.data


def test_journal_page_requires_login(client):
    resp = client.get("/journals/")
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]
