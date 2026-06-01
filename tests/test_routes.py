def test_index_redirects_to_login(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


def test_register_login_flow(client):
    resp = client.post("/auth/register", data={
        "username": "alice", "password": "pwd12345", "password2": "pwd12345",
    }, follow_redirects=False)
    assert resp.status_code == 302

    client.get("/auth/logout")

    resp = client.post("/auth/login", data={
        "username": "alice", "password": "pwd12345",
    }, follow_redirects=False)
    assert resp.status_code == 302


def test_document_crud(client):
    client.post("/auth/register", data={
        "username": "bob", "password": "pwd12345", "password2": "pwd12345",
    })
    # create
    resp = client.post("/documents/new", data={
        "title": "Test Paper",
        "document_type": "journal_article",
        "publication_year": "2024",
        "source_name": "Nature",
        "source_type": "journal",
        "publisher_name": "Springer",
        "authors_raw": "Alice | MIT | a@x.com\nBob | Stanford",
        "keywords_raw": "ml, graph",
        "abstract": "abc",
        "reading_status": "unread",
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert "Test Paper".encode() in resp.data

    # list & search
    resp = client.get("/documents/?q=Alice")
    assert "Test Paper".encode() in resp.data

    # detail
    resp = client.get("/documents/1")
    assert resp.status_code == 200
    assert b"Springer" in resp.data
    assert b"graph" in resp.data

    # delete
    resp = client.post("/documents/1/delete", follow_redirects=True)
    assert resp.status_code == 200


def test_tags_and_advanced_search(client):
    client.post("/auth/register", data={
        "username": "tagger", "password": "pwd12345", "password2": "pwd12345",
    })

    resp = client.post("/documents/new", data={
        "title": "Polymer Chemistry",
        "document_type": "journal_article",
        "publication_year": "2024",
        "source_name": "Journal of Chemistry",
        "source_type": "journal",
        "authors_raw": "Alice",
        "keywords_raw": "catalyst",
        "tags_raw": "化学, 高分子",
        "abstract": "polymer membrane study",
        "reading_status": "unread",
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert "化学".encode() in resp.data
    assert "高分子".encode() in resp.data

    client.post("/documents/new", data={
        "title": "Database Systems",
        "document_type": "conference_paper",
        "publication_year": "2019",
        "source_name": "VLDB",
        "source_type": "conference",
        "authors_raw": "Bob",
        "keywords_raw": "database",
        "tags_raw": "数据库",
        "abstract": "relational query processing",
        "reading_status": "unread",
    }, follow_redirects=True)

    for query in [
        "title=Polymer",
        "abstract=membrane",
        "author=Alice",
        "source=Chemistry",
        "keyword=catalyst",
        "tag=高分子",
        "year_from=2020&year_to=2025",
    ]:
        resp = client.get(f"/documents/?{query}")
        assert "Polymer Chemistry".encode() in resp.data
        assert b"Database Systems" not in resp.data

    resp = client.get("/documents/?q=高分子")
    assert "Polymer Chemistry".encode() in resp.data

    resp = client.get("/documents/?tag=化学&year_to=2020")
    assert "Polymer Chemistry".encode() not in resp.data

    resp = client.post("/documents/1/edit", data={
        "title": "Polymer Chemistry",
        "document_type": "journal_article",
        "publication_year": "2024",
        "source_name": "Journal of Chemistry",
        "source_type": "journal",
        "authors_raw": "Alice#1",
        "keywords_raw": "catalyst",
        "tags_raw": "材料",
        "abstract": "polymer membrane study",
        "reading_status": "unread",
    }, follow_redirects=True)
    assert "材料".encode() in resp.data
    assert "高分子".encode() not in resp.data

    resp = client.get("/library/")
    assert "材料".encode() in resp.data

    resp = client.get("/library/cleanup_scan")
    payload = resp.get_json()
    assert "高分子" in payload["orphans"]["tags"]


def test_document_new_persists_uploaded_attachment(login_client, upload_pdf, seeded_user_id, app):
    """POST /documents/new with an attachment should land a File row + on-disk file."""
    from pathlib import Path

    from flask import current_app

    from app.models import Document, File

    resp = login_client.post(
        "/documents/new",
        data={
            "title": "Attached Paper",
            "document_type": "journal_article",
            "publication_year": "2024",
            "source_name": "Nature",
            "source_type": "journal",
            "authors_raw": "Alice",
            "reading_status": "unread",
            "attachments": upload_pdf("attached.pdf"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        doc = Document.query.filter_by(user_id=seeded_user_id, title="Attached Paper").first()
        assert doc is not None
        files = File.query.filter_by(document_id=doc.id).all()
        assert len(files) == 1
        assert files[0].original_name == "attached.pdf"

        upload_root = Path(current_app.config["UPLOAD_FOLDER"])
        assert (upload_root / files[0].file_path).exists()


def test_document_edit_persists_uploaded_attachment(login_client, upload_pdf, seeded_user_id, app):
    """POST /documents/<id>/edit with a new attachment should also land it on disk."""
    from pathlib import Path

    from flask import current_app

    from app.extensions import db
    from app.models import Document, File

    with app.app_context():
        doc = Document(user_id=seeded_user_id, title="Editable")
        db.session.add(doc)
        db.session.commit()
        doc_id = doc.id

    resp = login_client.post(
        f"/documents/{doc_id}/edit",
        data={
            "title": "Editable",
            "document_type": "journal_article",
            "publication_year": "2024",
            "source_name": "Nature",
            "source_type": "journal",
            "authors_raw": "Alice",
            "reading_status": "unread",
            "attachments": upload_pdf("edited.pdf"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        files = File.query.filter_by(document_id=doc_id).all()
        assert len(files) == 1
        assert files[0].original_name == "edited.pdf"

        upload_root = Path(current_app.config["UPLOAD_FOLDER"])
        assert (upload_root / files[0].file_path).exists()
