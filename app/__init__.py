import os
from flask import Flask, redirect, url_for
from flask_login import current_user

from config import CONFIG_MAP
from .extensions import db, login_manager


def create_app(env: str = "dev") -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(CONFIG_MAP.get(env, CONFIG_MAP["dev"]))

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    from . import models  # noqa: F401  ensure models registered

    # Auto-create all tables on startup. Safe no-op when tables already exist;
    # silently skips when the DB isn't reachable yet (first-run wizard).
    with app.app_context():
        try:
            db.create_all()
        except Exception:
            pass

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(models.User, int(user_id))

    from .blueprints.auth import bp as auth_bp
    from .blueprints.documents import bp as documents_bp
    from .blueprints.categories import bp as categories_bp
    from .blueprints.library import bp as library_bp
    from .blueprints.bibtex import bp as bibtex_bp
    from .blueprints.settings import bp as settings_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(documents_bp, url_prefix="/documents")
    app.register_blueprint(categories_bp, url_prefix="/categories")
    app.register_blueprint(library_bp, url_prefix="/library")
    app.register_blueprint(bibtex_bp, url_prefix="/bibtex")
    app.register_blueprint(settings_bp, url_prefix="/settings")

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("documents.list_documents"))
        return redirect(url_for("auth.login"))

    @app.context_processor
    def inject_globals():
        return {"app_name": "Personal Library"}

    return app
