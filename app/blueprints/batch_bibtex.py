"""Batch PDF recognition + batch BibTeX import blueprint."""

import os
import time

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required

from ..extensions import db
from ..models import Category, Document, UserSetting
from ..services import bibtex_io, mineru_client
from ..services.ai_agent import record_activity
from ..services.file_io import save_uploaded_files

bp = Blueprint("batch_bibtex", __name__)

_ALLOWED_ATTACHMENT_EXTS = {"pdf"}


def _is_pdf(filename: str) -> bool:
    if not filename or "." not in filename:
        return False
    return filename.rsplit(".", 1)[-1].lower() in _ALLOWED_ATTACHMENT_EXTS


def _get_mineru_url(user_id: int) -> str:
    s = db.session.get(UserSetting, user_id)
    return (s.mineru_url if s and s.mineru_url else "").strip() or "http://127.0.0.1:8000"


@bp.route("/batch", methods=["GET"])
@login_required
def batch_page():
    uid = current_user.id
    categories = Category.query.filter_by(user_id=uid).order_by(Category.name).all()
    categories_payload = [{"id": c.id, "name": c.name} for c in categories]
    latest_doc = Document.query.order_by(Document.id.desc()).first()
    next_doc_id = (latest_doc.id if latest_doc else 0) + 1
    supported_types = bibtex_io.supported_entry_types()
    return render_template(
        "bibtex/batch.html",
        categories=categories_payload,
        mineru_url=_get_mineru_url(uid),
        next_doc_id=next_doc_id,
        supported_types=supported_types,
    )


@bp.route("/batch/recognize", methods=["POST"])
@login_required
def recognize():
    f = request.files.get("pdf")
    if not f or not f.filename:
        return jsonify(ok=False, error="未上传 PDF"), 400
    if not _is_pdf(f.filename):
        return jsonify(ok=False, error="仅支持 PDF 文件"), 400

    file_bytes = f.read()
    if not file_bytes:
        return jsonify(ok=False, error="PDF 文件为空"), 400

    try:
        parsed = mineru_client.parse_pdf(
            _get_mineru_url(current_user.id), file_bytes, f.filename, backend="pipeline"
        )
    except mineru_client.MineruError as e:
        return jsonify(ok=False, error=str(e)), 502

    record_activity(
        current_user.id,
        "pdf_recognize",
        "批量识别 PDF",
        {"filename": f.filename},
    )
    return jsonify(ok=True, filename=f.filename, markdown=parsed.get("md", ""))


@bp.route("/batch/import", methods=["POST"])
@login_required
def import_one():
    f = request.files.get("pdf")
    bib_text = (request.form.get("bib_text") or "").strip()
    category_id = request.form.get("category_id", type=int)

    if not f or not f.filename:
        return jsonify(ok=False, error="未上传 PDF"), 400
    if not _is_pdf(f.filename):
        return jsonify(ok=False, error="附件必须是 PDF"), 400
    if not bib_text:
        return jsonify(ok=False, reason="bib_empty")

    try:
        entries = bibtex_io.parse_entries(bib_text)
    except Exception as e:
        return jsonify(ok=False, reason="bib_parse_failed", error_detail=str(e))

    if len(entries) != 1:
        return jsonify(
            ok=False,
            reason="bib_multi_entry",
            error_detail=f"该输入框应只含 1 个条目，实际 {len(entries)} 个",
        )

    uid = current_user.id
    try:
        result = bibtex_io.import_single_entry(entries[0], uid, category_id)
    except Exception as e:
        db.session.rollback()
        return jsonify(ok=False, reason="save_failed", error_detail=str(e))

    if result["skipped_reason"]:
        db.session.rollback()
        return jsonify(ok=False, reason="duplicate", error_detail=result["skipped_reason"])

    doc = result["created"]
    saved_paths = []
    try:
        saved_paths, _ = save_uploaded_files(doc, [f], uid)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        try:
            f.close()
        except Exception:
            pass
        cleanup_errors = []
        for p in saved_paths:
            try:
                for _ in range(10):
                    try:
                        p.unlink(missing_ok=True)
                        if p.exists():
                            os.remove(p)
                        break
                    except PermissionError:
                        time.sleep(0.05)
                if p.exists():
                    raise PermissionError(f"failed to unlink {p}")
            except Exception as unlink_err:
                cleanup_errors.append(f"{p}: {unlink_err}")
        detail = str(e)
        if cleanup_errors:
            detail += " | cleanup_errors=" + "; ".join(cleanup_errors)
        return jsonify(ok=False, reason="save_failed", error_detail=detail)

    record_activity(
        current_user.id,
        "bibtex_batch_import",
        "批量导入 BibTeX + PDF",
        {"document_id": doc.id, "filename": f.filename},
    )
    return jsonify(ok=True, document_id=doc.id, title=doc.title)


@bp.route("/batch/health", methods=["GET"])
@login_required
def batch_health():
    base_url = _get_mineru_url(current_user.id)
    try:
        info = mineru_client.health_check(base_url)
    except mineru_client.MineruError as e:
        return jsonify(ok=False, error=str(e), url=base_url)
    return jsonify(ok=True, info=info, url=base_url)
