import io

from werkzeug.datastructures import FileStorage

from app.extensions import db
from app.models import Document, File, User
from app.services.file_io import save_uploaded_files


def _make_filestorage(name="sample.pdf", content=b"%PDF-1.1\n%dummy\n"):
    return FileStorage(
        stream=io.BytesIO(content),
        filename=name,
        content_type="application/pdf",
    )


def test_save_uploaded_files_creates_file_record_and_writes_disk(app):
    with app.app_context():
        u = User(username="u1", email="u1@x.com")
        u.set_password("pw123456")
        db.session.add(u)
        db.session.flush()
        doc = Document(user_id=u.id, title="T")
        db.session.add(doc)
        db.session.flush()

        fs = _make_filestorage("a.pdf", b"%PDF-1.1\nhello\n")
        saved, skipped = save_uploaded_files(doc, [fs], u.id)
        db.session.commit()

        assert len(saved) == 1
        assert saved[0].exists()
        assert skipped == []
        recs = File.query.filter_by(document_id=doc.id).all()
        assert len(recs) == 1
        assert recs[0].original_name == "a.pdf"
        assert recs[0].mime_type == "application/pdf"


def test_save_uploaded_files_skips_disallowed_extension(app):
    with app.app_context():
        u = User(username="u2", email="u2@x.com")
        u.set_password("pw123456")
        db.session.add(u)
        db.session.flush()
        doc = Document(user_id=u.id, title="T")
        db.session.add(doc)
        db.session.flush()

        fs = _make_filestorage("notes.exe", b"MZ\x90\x00")
        saved, skipped = save_uploaded_files(doc, [fs], u.id)

        assert saved == []
        assert skipped == ["notes.exe"]
        assert File.query.count() == 0


def test_save_uploaded_files_skips_empty_filename(app):
    with app.app_context():
        u = User(username="u3", email="u3@x.com")
        u.set_password("pw123456")
        db.session.add(u)
        db.session.flush()
        doc = Document(user_id=u.id, title="T")
        db.session.add(doc)
        db.session.flush()

        fs = _make_filestorage("", b"")
        saved, skipped = save_uploaded_files(doc, [fs], u.id)

        assert saved == []
        assert skipped == []
