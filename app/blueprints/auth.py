from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user

from ..extensions import db
from ..models import User
from ..services.ai_agent import record_activity

bp = Blueprint("auth", __name__)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("documents.list_documents"))
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip() or None
        password = request.form.get("password") or ""
        password2 = request.form.get("password2") or ""

        if not username or not password:
            flash("用户名和密码必填", "danger")
            return render_template("auth/register.html")
        if password != password2:
            flash("两次密码不一致", "danger")
            return render_template("auth/register.html")
        if User.query.filter_by(username=username).first():
            flash("用户名已存在", "danger")
            return render_template("auth/register.html")
        if email and User.query.filter_by(email=email).first():
            flash("邮箱已被注册", "danger")
            return render_template("auth/register.html")

        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        record_activity(user.id, "auth_register", "注册并登录")
        flash("注册成功！", "success")
        return redirect(url_for("documents.list_documents"))
    return render_template("auth/register.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("documents.list_documents"))
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            flash("用户名或密码错误", "danger")
            return render_template("auth/login.html")
        login_user(user, remember=bool(request.form.get("remember")))
        record_activity(user.id, "auth_login", "登录系统")
        next_url = request.args.get("next") or url_for("documents.list_documents")
        return redirect(next_url)
    return render_template("auth/login.html")


@bp.route("/logout")
@login_required
def logout():
    record_activity(current_user.id, "auth_logout", "退出登录")
    logout_user()
    flash("已退出登录", "info")
    return redirect(url_for("auth.login"))
