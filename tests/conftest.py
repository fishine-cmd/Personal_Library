import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import User  # noqa: E402


@pytest.fixture
def app():
    app = create_app("test")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def user(app):
    with app.app_context():
        u = User(username="tester", email="t@example.com")
        u.set_password("pw123456")
        db.session.add(u)
        db.session.commit()
        return u.id


@pytest.fixture
def login_client(client):
    """Test client that has registered + logged in a user. Username 'tester'."""
    client.post(
        "/auth/register",
        data={"username": "tester", "password": "pw123456", "password2": "pw123456"},
    )
    return client


@pytest.fixture
def seeded_user_id(app, login_client):
    """Return the id of the user logged in via login_client."""
    with app.app_context():
        u = User.query.filter_by(username="tester").first()
        return u.id


_TINY_PDF = (
    b"%PDF-1.1\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
    b"xref\n0 4\n0000000000 65535 f \n"
    b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n0\n%%EOF\n"
)


@pytest.fixture
def tiny_pdf_bytes():
    return _TINY_PDF


@pytest.fixture
def upload_pdf(tiny_pdf_bytes):
    """Build (BytesIO, filename) tuple ready for Werkzeug test client uploads."""
    def _make(filename="sample.pdf"):
        return (io.BytesIO(tiny_pdf_bytes), filename)

    return _make


@pytest.fixture
def mock_mineru(monkeypatch):
    """Patch mineru_client.parse_pdf to return a fixed payload."""
    calls = []

    def fake_parse_pdf(base_url, file_bytes, filename, **kwargs):
        calls.append({"url": base_url, "filename": filename, "kwargs": kwargs})
        return {"md": f"# {filename}\n\nFake markdown body.", "content_list": []}

    from app.services import mineru_client

    monkeypatch.setattr(mineru_client, "parse_pdf", fake_parse_pdf)
    return calls
