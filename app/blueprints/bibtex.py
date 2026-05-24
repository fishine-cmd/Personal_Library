from flask import Blueprint, render_template, request, redirect, url_for, flash, Response
from flask_login import login_required, current_user

from ..models import Document
from ..services import bibtex_io

bp = Blueprint("bibtex", __name__)


@bp.route("/import", methods=["GET", "POST"])
@login_required
def import_form():
    if request.method == "POST":
        text = (request.form.get("bib_text") or "").strip()
        f = request.files.get("bib_file")
        if f and f.filename:
            text = f.read().decode("utf-8", errors="replace")
        if not text:
            flash("请粘贴 BibTeX 内容或选择 .bib 文件", "danger")
            return redirect(url_for("bibtex.import_form"))
        try:
            created, skipped = bibtex_io.import_bibtex(text, current_user.id)
        except Exception as e:
            flash(f"解析失败: {e}", "danger")
            return redirect(url_for("bibtex.import_form"))
        flash(f"导入完成：新建 {created} 篇，跳过 {skipped} 篇（重复或无标题）", "success")
        return redirect(url_for("documents.list_documents"))
    return render_template("bibtex/import.html")


@bp.route("/export")
@login_required
def export_all():
    docs = Document.query.filter_by(user_id=current_user.id).all()
    bib = bibtex_io.export_bibtex(docs)
    return Response(
        bib,
        mimetype="application/x-bibtex",
        headers={"Content-Disposition": "attachment; filename=library.bib"},
    )


@bp.route("/export/<int:doc_id>")
@login_required
def export_one(doc_id):
    doc = Document.query.filter_by(id=doc_id, user_id=current_user.id).first_or_404()
    bib = bibtex_io.export_bibtex([doc])
    return Response(
        bib,
        mimetype="application/x-bibtex",
        headers={"Content-Disposition": f"attachment; filename=doc{doc_id}.bib"},
    )
