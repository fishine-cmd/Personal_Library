import os
from flask import Flask, redirect, url_for
from flask_login import current_user

from config import CONFIG_MAP# 导入配置映射（开发/生产环境配置）
from .extensions import db, login_manager# 导入已初始化的扩展：数据库database、登录管理器 login_manager

# 应用工厂函数：接收环境参数（默认 dev 开发环境），返回 Flask 实例
def create_app(env: str = "dev") -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(CONFIG_MAP.get(env, CONFIG_MAP["dev"]))

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    from . import models  # noqa: F401  让 linter 不提示“未使用导入”

    # 启动时自动创建所有数据库表(表已存在则不执行)
    # 数据库连不上时不阻断启动，但要在日志里留痕，便于排查
    with app.app_context():
        try:
            db.create_all()
        except Exception:
            app.logger.exception("db.create_all() failed during app startup")

    # 登录管理器的用户加载函数
    # Flask-Login 用它通过 user_id 获取用户对象
    @login_manager.user_loader
    def load_user(user_id):
        # 根据用户 ID 查询 User 模型并返回
        return db.session.get(models.User, int(user_id))

    # 导入各个蓝图
    from .blueprints.auth import bp as auth_bp
    from .blueprints.documents import bp as documents_bp
    from .blueprints.categories import bp as categories_bp
    from .blueprints.library import bp as library_bp
    from .blueprints.bibtex import bp as bibtex_bp
    from .blueprints.batch_bibtex import bp as batch_bibtex_bp
    from .blueprints.settings import bp as settings_bp
    from .blueprints.ai_agent import bp as ai_agent_bp
    from .blueprints.journals import bp as journals_bp

    # 注册蓝图，并设置 URL 前缀
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(documents_bp, url_prefix="/documents")
    app.register_blueprint(categories_bp, url_prefix="/categories")
    app.register_blueprint(library_bp, url_prefix="/library")
    app.register_blueprint(bibtex_bp, url_prefix="/bibtex")
    app.register_blueprint(batch_bibtex_bp, url_prefix="/bibtex")
    app.register_blueprint(settings_bp, url_prefix="/settings")
    app.register_blueprint(ai_agent_bp, url_prefix="/ai-agent")
    app.register_blueprint(journals_bp, url_prefix="/journals")

    # 根路由 /
    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("documents.list_documents"))
        return redirect(url_for("auth.login"))

    # 全局模板变量注入
    @app.context_processor
    def inject_globals():
        return {"app_name": "Personal Library"}

    return app
