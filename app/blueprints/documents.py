import os
import uuid
from pathlib import Path

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    current_app,
    send_from_directory,
    jsonify,
    abort,
)
from flask_login import login_required, current_user
from sqlalchemy import or_
from werkzeug.utils import secure_filename

from ..extensions import db
from ..models import (
    Document,
    DocumentAuthor,
    Category,
    Author,
    AuthorCode,
    Keyword,
    Source,
    Tag,
    File,
    UserSetting,
)
from ..services import upsert, mineru_client, pdf_metadata, dict_cleanup
from ..services.ai_agent import record_activity
from ..services.file_io import save_uploaded_files as _save_uploaded_files_impl

bp = Blueprint("documents", __name__)


def _allowed_file(filename: str) -> bool:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in current_app.config["ALLOWED_EXTENSIONS"]


def _expand_category_ids(root_id: int, user_id: int) -> list[int]:
    """Return root_id plus the IDs of every descendant (recursive). Used so
    that filtering by a parent category includes documents in its sub-categories."""
    cats = Category.query.filter_by(user_id=user_id).all()
    by_parent: dict = {}
    for c in cats:
        by_parent.setdefault(c.parent_id, []).append(c.id)
    found: set[int] = set()
    stack = [root_id]
    while stack:
        cid = stack.pop()
        if cid in found:
            continue
        found.add(cid)
        stack.extend(by_parent.get(cid, []))
    return list(found)


def _ordered_categories(user_id: int) -> list:
    """Flatten categories into tree order so each parent is followed by its
    descendants. Each Category gets a `.depth` attribute (0 = top-level)
    for the template to render indentation."""
    cats = Category.query.filter_by(user_id=user_id).order_by(Category.name).all()
    by_parent: dict = {}
    for c in cats:
        by_parent.setdefault(c.parent_id, []).append(c)

    ordered: list = []

    def visit(parent_id, depth):
        for c in by_parent.get(parent_id, []):
            c.depth = depth
            ordered.append(c)
            visit(c.id, depth + 1)

    visit(None, 0)
    return ordered


def _save_uploaded_files(document: Document, files):
    _, skipped = _save_uploaded_files_impl(document, files, current_user.id)
    for name in skipped:
        flash(f"跳过不允许的文件类型: {name}", "warning")


def _persist_document_form(document: Document, form, files):
    document.title = form.get("title", "").strip()
    document.abstract = form.get("abstract") or None
    document.document_type = form.get("document_type") or "journal_article"
    document.publication_year = int(form["publication_year"]) if form.get("publication_year") else None
    document.volume = form.get("volume") or None
    document.issue = form.get("issue") or None
    document.pages = form.get("pages") or None
    document.doi = form.get("doi") or None
    document.notes = form.get("notes") or None
    document.rating = int(form["rating"]) if form.get("rating") else None
    document.reading_status = form.get("reading_status") or "unread"

    cat_id = form.get("category_id")
    if cat_id:
        cat = Category.query.filter_by(id=int(cat_id), user_id=current_user.id).first()
        document.category = cat
    else:
        document.category = None

    uid = current_user.id
    source_name = (form.get("source_name") or "").strip()
    source_type = form.get("source_type") or "journal"
    publisher_name = (form.get("publisher_name") or "").strip()
    document.source = upsert.get_or_create_source(source_name, uid, source_type, publisher_name)

    # authors: textarea, one per line, "name[#code] | aff1; aff2"
    parsed_authors = upsert.parse_authors_field(form.get("authors_raw", ""))

    # 在 upsert 之前先按 (name, code) 去重，避免 allocate_new_author 被重复调用
    seen, deduped = set(), []
    for entry in parsed_authors:
        key = (entry["name"], entry["code"])  # code 是 None / int / "new"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    if len(deduped) < len(parsed_authors):
        flash(f"已自动去除 {len(parsed_authors) - len(deduped)} 个重复作者", "info")
    parsed_authors = deduped

    document.author_links.clear()
    db.session.flush()
    seen_author_ids = set()
    order = 0 # ← 先初始化计数器
    for entry in parsed_authors:# ← 去掉 enumerate
        code_marker = entry["code"]
        if code_marker == "new":
            author = upsert.allocate_new_author(entry["name"], uid)
        elif isinstance(code_marker, int):
            author = upsert.get_or_create_author(entry["name"], uid, code=code_marker)
        else:
            author = upsert.get_or_create_author(entry["name"], uid)
        if author.id in seen_author_ids:
            continue
        seen_author_ids.add(author.id)
        order += 1# ← 只在通过去重后才自增
        for aff_name in entry["affiliations"]:
            aff = upsert.get_or_create_affiliation(aff_name, uid)
            if aff not in author.affiliations:
                author.affiliations.append(aff)
        db.session.add(
            DocumentAuthor(
                document_id=document.id, author_id=author.id, author_order=order   # ← 用 order
            )
        )
    # keywords
    document.keywords.clear()
    raw_kws = upsert.parse_csv_list(form.get("keywords_raw", ""))
    seen, deduped = set(), []
    for k in raw_kws:
        if k in seen:
            continue
        seen.add(k)
        deduped.append(k)
    if len(deduped) < len(raw_kws):
        flash(f"已自动去除 {len(raw_kws) - len(deduped)} 个重复关键词", "info")
    for kw_name in deduped:
        document.keywords.append(upsert.get_or_create_keyword(kw_name, uid))

    # tags
    document.tags.clear()
    raw_tags = upsert.parse_csv_list(form.get("tags_raw", ""))
    seen, deduped = set(), []
    for tag_name in raw_tags:
        if tag_name in seen:
            continue
        seen.add(tag_name)
        deduped.append(tag_name)
    if len(deduped) < len(raw_tags):
        flash(f"已自动去除 {len(raw_tags) - len(deduped)} 个重复标签", "info")
    for tag_name in deduped:
        document.tags.append(upsert.get_or_create_tag(tag_name, uid))


@bp.route("/")
@login_required
def list_documents():
    q = (request.args.get("q") or "").strip()
    category_id = request.args.get("category", type=int)
    doc_type = request.args.get("type")
    year = request.args.get("year", type=int)
    year_from = request.args.get("year_from", type=int)
    year_to = request.args.get("year_to", type=int)
    title = (request.args.get("title") or "").strip()
    abstract = (request.args.get("abstract") or "").strip()
    author = (request.args.get("author") or "").strip()
    source = (request.args.get("source") or "").strip()
    keyword = (request.args.get("keyword") or "").strip()
    tag = (request.args.get("tag") or "").strip()

    query = Document.query.filter_by(user_id=current_user.id)

    if category_id:
        expanded_ids = _expand_category_ids(category_id, current_user.id)
        query = query.filter(Document.category_id.in_(expanded_ids))
    if doc_type:
        query = query.filter_by(document_type=doc_type)
    if year:
        query = query.filter_by(publication_year=year)
    if year_from:
        query = query.filter(Document.publication_year >= year_from)
    if year_to:
        query = query.filter(Document.publication_year <= year_to)

    if title:
        query = query.filter(Document.title.ilike(f"%{title}%"))
    if abstract:
        query = query.filter(Document.abstract.ilike(f"%{abstract}%"))
    if author:
        like = f"%{author}%"
        query = query.filter(
            Document.author_links.any(
                DocumentAuthor.author.has(Author.name.ilike(like))
            )
        )
    if source:
        query = query.filter(Document.source.has(Source.name.ilike(f"%{source}%")))
    if keyword:
        query = query.filter(Document.keywords.any(Keyword.name.ilike(f"%{keyword}%")))
    if tag:
        query = query.filter(Document.tags.any(Tag.name.ilike(f"%{tag}%")))

    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Document.title.ilike(like),
                Document.abstract.ilike(like),
                Document.doi.ilike(like),
                Document.author_links.any(
                    DocumentAuthor.author.has(Author.name.ilike(like))
                ),
                Document.keywords.any(Keyword.name.ilike(like)),
                Document.tags.any(Tag.name.ilike(like)),
                Document.source.has(Source.name.ilike(like)),
            )
        )

    documents = query.order_by(Document.updated_at.desc()).all()
    categories = _ordered_categories(current_user.id)
    active_category_name = None
    if category_id:
        cat = Category.query.filter_by(
            id=category_id, user_id=current_user.id
        ).first()
        active_category_name = cat.name if cat else None
    return render_template(
        "documents/list.html",
        documents=documents,
        categories=categories,
        q=q,
        active_category=category_id,
        active_category_name=active_category_name,
        active_type=doc_type,
        active_year=year,
        active_year_from=year_from,
        active_year_to=year_to,
        title=title,
        abstract=abstract,
        author=author,
        source=source,
        keyword=keyword,
        tag=tag,
    )


@bp.route("/<int:doc_id>")
@login_required
def detail(doc_id):
    doc = Document.query.filter_by(id=doc_id, user_id=current_user.id).first_or_404()
    return render_template("documents/detail.html", doc=doc)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        if not title:
            flash("文献标题必填", "danger")
            return redirect(url_for("documents.new"))
        doc = Document(user_id=current_user.id, title=title)
        db.session.add(doc)
        db.session.flush()
        try:
            _persist_document_form(doc, request.form, request.files.getlist("attachments"))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f"保存失败: {e}", "danger")
            return redirect(url_for("documents.new"))
        record_activity(
            current_user.id,
            "document_create",
            "Create document",
            {"document_id": doc.id, "title": doc.title},
        )
        flash("文献已创建", "success")
        return redirect(url_for("documents.detail", doc_id=doc.id))

    categories = Category.query.filter_by(user_id=current_user.id).order_by(Category.name).all()
    return render_template(
        "documents/edit.html", doc=None, categories=categories, authors_text=""
    )


@bp.route("/<int:doc_id>/edit", methods=["GET", "POST"])
@login_required
def edit(doc_id):
    doc = Document.query.filter_by(id=doc_id, user_id=current_user.id).first_or_404()
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        if not title:
            flash("文献标题必填", "danger")
            return redirect(url_for("documents.edit", doc_id=doc_id))
        try:
            _persist_document_form(doc, request.form, request.files.getlist("attachments"))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f"保存失败: {e}", "danger")
            return redirect(url_for("documents.edit", doc_id=doc_id))
        record_activity(
            current_user.id,
            "document_edit",
            "Edit document",
            {"document_id": doc.id, "title": doc.title},
        )
        flash("已保存", "success")
        return redirect(url_for("documents.detail", doc_id=doc.id))

    categories = Category.query.filter_by(user_id=current_user.id).order_by(Category.name).all()
    authors_text = upsert.authors_field_to_text(doc.author_links)
    return render_template(
        "documents/edit.html",
        doc=doc,
        categories=categories,
        authors_text=authors_text,
    )


def _build_combined_markdown(filename: str, meta: dict, raw_md: str) -> str:
    """Pack heuristic suggestions + MinerU raw markdown into one .md string."""
    from datetime import datetime, timezone

    def _or(value, fallback="—"):
        if value is None or value == "" or value == []:
            return fallback
        return value

    title = _or(meta.get("title"))
    authors = meta.get("authors") or []
    affiliations = meta.get("affiliations") or []
    emails = meta.get("emails") or []
    keywords = meta.get("keywords") or []
    abstract = (meta.get("abstract") or "").strip()
    doi = _or(meta.get("doi"))
    year = _or(meta.get("year"))
    source = _or(meta.get("source"))
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines: list[str] = [
        f"# 识别结果 · {filename}",
        "",
        f"> 识别时间：{ts}  ·  解析引擎：MinerU",
        "",
        "## 建议字段（启发式抽取，请人工核对）",
        "",
        f"- **标题**：{title}",
        f"- **作者**：{'  '.join(f'`{a}`' for a in authors) if authors else '—'}",
        f"- **作者邮箱**：{', '.join(emails) if emails else '—'}",
        f"- **作者单位**：{'; '.join(affiliations) if affiliations else '—'}",
        f"- **DOI**：{doi}",
        f"- **出版年份**：{year}",
        f"- **来源（期刊/会议）**：{source}",
        f"- **关键词**：{', '.join(keywords) if keywords else '—'}",
        "",
        "### 摘要",
        "",
        abstract if abstract else "—",
        "",
        "---",
        "",
        "## MinerU 原始解析结果",
        "",
        raw_md or "*(MinerU 未返回 markdown 内容)*",
        "",
    ]
    return "\n".join(lines)


@bp.route("/api/author_lookup")
@login_required
def author_lookup():
    """Disambiguation helper for the author textarea.

    Returns every Author sharing this name (across users, since the dictionary
    table is shared), with one sample document from the current user (if any)
    to help identify the right person.
    """
    name = (request.args.get("name") or "").strip()
    if not name:
        return jsonify(name="", authors=[], next_code=1)

    authors = upsert.peek_authors_by_name(name, current_user.id)
    counter = db.session.get(AuthorCode, (current_user.id, name))
    next_code = counter.next_code if counter else 1

    items = []
    for a in authors:
        row = (
            db.session.query(Document)
            .join(DocumentAuthor, DocumentAuthor.document_id == Document.id)
            .filter(
                DocumentAuthor.author_id == a.id,
                Document.user_id == current_user.id,
            )
            .order_by(Document.updated_at.desc())
            .first()
        )
        sample_doc = (
            {"id": row.id, "title": row.title, "year": row.publication_year}
            if row else None
        )
        items.append({
            "id": a.id,
            "code": a.code,
            "affiliations": [af.name for af in a.affiliations],
            "sample_doc": sample_doc,
        })

    return jsonify(name=name, authors=items, next_code=next_code)


@bp.route("/recognize_pdf", methods=["POST"])
@login_required
def recognize_pdf():
    f = request.files.get("pdf")
    if not f or not f.filename:
        return jsonify(ok=False, error="未上传 PDF"), 400
    if not f.filename.lower().endswith(".pdf"):
        return jsonify(ok=False, error="仅支持 PDF 文件"), 400

    s = db.session.get(UserSetting, current_user.id)
    mineru_url = (s.mineru_url if s and s.mineru_url else "").strip() or "http://127.0.0.1:8000"

    file_bytes = f.read()
    if not file_bytes:
        return jsonify(ok=False, error="PDF 文件为空"), 400

    try:
        parsed = mineru_client.parse_pdf(
            mineru_url, file_bytes, f.filename, backend="pipeline"
        )
    except mineru_client.MineruError as e:
        return jsonify(ok=False, error=str(e)), 502

    meta = pdf_metadata.extract_metadata(parsed)
    markdown = _build_combined_markdown(f.filename, meta, parsed.get("md", ""))

    record_activity(
        current_user.id,
        "pdf_recognize",
        "Recognize PDF",
        {"filename": f.filename},
    )
    return jsonify(
        ok=True,
        filename=f.filename,
        suggested_fields={
            "title": meta.get("title", ""),
            "authors": meta.get("authors", []),
            "affiliations": meta.get("affiliations", []),
            "emails": meta.get("emails", []),
            "abstract": meta.get("abstract", ""),
            "keywords": meta.get("keywords", []),
            "doi": meta.get("doi", ""),
            "year": meta.get("year"),
            "source": meta.get("source", ""),
        },
        markdown=markdown,
    )


@bp.route("/<int:doc_id>/delete", methods=["POST"])
@login_required
def delete(doc_id):
    doc = Document.query.filter_by(id=doc_id, user_id=current_user.id).first_or_404()

    related_authors = {link.author for link in doc.author_links}
    related_keywords = set(doc.keywords)
    related_tags = set(doc.tags)
    related_source = doc.source

    upload_root = Path(current_app.config["UPLOAD_FOLDER"])
    for f in doc.files:
        try:
            (upload_root / f.file_path).unlink(missing_ok=True)
        except Exception:
            pass
    db.session.delete(doc)
    db.session.flush()

    cleaned = dict_cleanup.prune_orphans_around_document(
        related_authors, related_keywords, related_tags, related_source
    )
    db.session.commit()
    record_activity(
        current_user.id,
        "document_delete",
        "Delete document",
        {"document_id": doc_id},
    )

    labels = {
        "keywords": "关键词", "tags": "标签", "authors": "作者", "affiliations": "单位",
        "sources": "来源", "publishers": "出版社",
    }
    parts = [f"{v} {labels[k]}" for k, v in cleaned.items() if k in labels and v]
    extra = "（顺带清理 " + " · ".join(parts) + "）" if parts else ""
    flash(f"文献已删除{extra}", "info")
    return redirect(url_for("documents.list_documents"))


@bp.route("/<int:doc_id>/file/<int:file_id>")
@login_required
def download_file(doc_id, file_id):
    doc = Document.query.filter_by(id=doc_id, user_id=current_user.id).first_or_404()
    file_record = File.query.filter_by(id=file_id, document_id=doc.id).first_or_404()
    record_activity(
        current_user.id,
        "file_download",
        "Download attachment",
        {"document_id": doc.id, "file_id": file_id, "filename": file_record.original_name},
    )
    upload_root = current_app.config["UPLOAD_FOLDER"]
    return send_from_directory(
        upload_root,
        file_record.file_path,
        download_name=file_record.original_name,
        as_attachment=request.args.get("download") == "1",
    )


@bp.route("/<int:doc_id>/file/<int:file_id>/delete", methods=["POST"])
@login_required
def delete_file(doc_id, file_id):
    doc = Document.query.filter_by(id=doc_id, user_id=current_user.id).first_or_404()
    file_record = File.query.filter_by(id=file_id, document_id=doc.id).first_or_404()
    upload_root = Path(current_app.config["UPLOAD_FOLDER"])
    try:
        (upload_root / file_record.file_path).unlink(missing_ok=True)
    except Exception:
        pass
    db.session.delete(file_record)
    db.session.commit()
    record_activity(
        current_user.id,
        "file_delete",
        "Delete attachment",
        {"document_id": doc.id, "file_id": file_id, "filename": file_record.original_name},
    )
    flash("附件已删除", "info")
    return redirect(url_for("documents.detail", doc_id=doc_id))
