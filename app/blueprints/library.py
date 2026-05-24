from flask import Blueprint, render_template, jsonify, request, redirect, url_for, flash
from flask_login import login_required, current_user

from ..extensions import db
from ..models import Author, Affiliation, Publisher, Source
from ..services import dict_cleanup

bp = Blueprint("library", __name__)


@bp.route("/")
@login_required
def index():
    uid = current_user.id
    authors = Author.query.filter_by(user_id=uid).order_by(Author.name).all()
    affiliations = (
        Affiliation.query.filter_by(user_id=uid).order_by(Affiliation.name).all()
    )
    publishers = (
        Publisher.query.filter_by(user_id=uid).order_by(Publisher.name).all()
    )
    sources = Source.query.filter_by(user_id=uid).order_by(Source.name).all()
    return render_template(
        "library/index.html",
        authors=authors,
        affiliations=affiliations,
        publishers=publishers,
        sources=sources,
    )


@bp.route("/authors/<int:author_id>/delete", methods=["POST"])
@login_required
def delete_author(author_id):
    a = Author.query.filter_by(id=author_id, user_id=current_user.id).first()
    if a and not a.document_links:
        db.session.delete(a)
        db.session.commit()
        flash("作者已删除", "info")
    else:
        flash("作者不存在或关联了文献，无法删除", "warning")
    return redirect(url_for("library.index"))


@bp.route("/affiliations/<int:aff_id>/delete", methods=["POST"])
@login_required
def delete_affiliation(aff_id):
    a = Affiliation.query.filter_by(id=aff_id, user_id=current_user.id).first()
    if a and not a.authors:
        db.session.delete(a)
        db.session.commit()
        flash("单位已删除", "info")
    else:
        flash("单位不存在或关联了作者，无法删除", "warning")
    return redirect(url_for("library.index"))


@bp.route("/publishers/<int:pub_id>/delete", methods=["POST"])
@login_required
def delete_publisher(pub_id):
    p = Publisher.query.filter_by(id=pub_id, user_id=current_user.id).first()
    if p and not p.sources:
        db.session.delete(p)
        db.session.commit()
        flash("出版社已删除", "info")
    else:
        flash("出版社不存在或关联了来源，无法删除", "warning")
    return redirect(url_for("library.index"))


@bp.route("/sources/<int:src_id>/delete", methods=["POST"])
@login_required
def delete_source(src_id):
    s = Source.query.filter_by(id=src_id, user_id=current_user.id).first()
    if s and not s.documents:
        db.session.delete(s)
        db.session.commit()
        flash("来源已删除", "info")
    else:
        flash("来源不存在或关联了文献，无法删除", "warning")
    return redirect(url_for("library.index"))


# ---- Cleanup (orphan + duplicate detection) ----

@bp.route("/cleanup_scan")
@login_required
def cleanup_scan():
    uid = current_user.id
    orphans = dict_cleanup.scan_orphans(uid)
    duplicates = dict_cleanup.find_potential_duplicates(uid)
    return jsonify(
        orphans={k: [item.name for item in v] for k, v in orphans.items()},
        duplicates={
            k: [[item.name for item in group] for group in groups]
            for k, groups in duplicates.items()
        },
    )


@bp.route("/cleanup_apply", methods=["POST"])
@login_required
def cleanup_apply():
    try:
        counts = dict_cleanup.delete_all_orphans(current_user.id)
    except Exception as e:
        db.session.rollback()
        return jsonify(ok=False, error=str(e))
    return jsonify(ok=True, deleted=counts)


# ---- JSON autocomplete endpoints ----

@bp.route("/api/sources")
@login_required
def api_sources():
    uid = current_user.id
    return jsonify(
        [s.name for s in Source.query.filter_by(user_id=uid).order_by(Source.name).all()]
    )


@bp.route("/api/publishers")
@login_required
def api_publishers():
    uid = current_user.id
    return jsonify(
        [p.name for p in Publisher.query.filter_by(user_id=uid).order_by(Publisher.name).all()]
    )


@bp.route("/api/authors")
@login_required
def api_authors():
    uid = current_user.id
    return jsonify(
        [a.name for a in Author.query.filter_by(user_id=uid).order_by(Author.name).all()]
    )


@bp.route("/api/affiliations")
@login_required
def api_affiliations():
    uid = current_user.id
    return jsonify(
        [a.name for a in Affiliation.query.filter_by(user_id=uid).order_by(Affiliation.name).all()]
    )
