"""桌面启动器：把 Flask 应用嵌入 pywebview 原生窗口。

首次运行会弹出配置向导收集 MySQL 连接信息；配置持久化到
%APPDATA%\\PersonalLibrary\\config.json，之后启动直接进入主界面。
"""

import json
import os
import secrets
import socket
import sys
import threading
from pathlib import Path
from urllib.parse import quote_plus

import webview

APP_NAME = "PersonalLibrary"
WINDOW_TITLE = "Personal Library · 个人文献管理"


def appdata_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData/Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    d = base / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


CONFIG_FILE = appdata_dir() / "config.json"
UPLOAD_DIR = appdata_dir() / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict | None:
    if not CONFIG_FILE.exists():
        return None
    try:
        return json.loads(CONFIG_FILE.read_text("utf-8"))
    except Exception:
        return None


def save_config(cfg: dict) -> None:
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), "utf-8")


def find_free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def ensure_database(cfg: dict) -> None:
    import pymysql
    conn = pymysql.connect(
        host=cfg["host"],
        port=int(cfg["port"]),
        user=cfg["user"],
        password=cfg["password"],
        charset="utf8mb4",
        connect_timeout=5,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{cfg['database']}` "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        conn.close()


def build_database_url(cfg: dict) -> str:
    return (
        f"mysql+pymysql://{cfg['user']}:{quote_plus(cfg['password'])}"
        f"@{cfg['host']}:{cfg['port']}/{cfg['database']}?charset=utf8mb4"
    )


def make_main_app(cfg: dict):
    os.environ["DATABASE_URL"] = build_database_url(cfg)
    os.environ["UPLOAD_FOLDER"] = str(UPLOAD_DIR)
    os.environ["FLASK_SECRET_KEY"] = cfg.get("secret_key") or secrets.token_hex(32)

    from app import create_app
    from app.extensions import db

    flask_app = create_app("prod")
    with flask_app.app_context():
        db.create_all()
    return flask_app


def run_server_in_thread(flask_app, port: int):
    from werkzeug.serving import make_server
    server = make_server("127.0.0.1", port, flask_app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


SETUP_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>首次配置</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
<style>body{background:#f7f8fa;padding:24px;font-family:-apple-system,Segoe UI,sans-serif;}</style>
</head>
<body>
<div class="container" style="max-width:480px">
  <h4 class="mb-1">连接 MySQL</h4>
  <p class="text-muted small mb-3">
    首次使用需要填写 MySQL 服务器信息。<br>
    配置保存在 <code>%APPDATA%\\PersonalLibrary\\config.json</code>，删除该文件可重新配置。
  </p>
  <div id="alert"></div>
  <form id="f" class="row g-3">
    <div class="col-8"><label class="form-label">主机</label>
      <input class="form-control" name="host" value="localhost" required></div>
    <div class="col-4"><label class="form-label">端口</label>
      <input class="form-control" name="port" value="3306" required></div>
    <div class="col-12"><label class="form-label">用户名</label>
      <input class="form-control" name="user" value="root" required></div>
    <div class="col-12"><label class="form-label">密码</label>
      <input type="password" class="form-control" name="password"></div>
    <div class="col-12"><label class="form-label">数据库名</label>
      <input class="form-control" name="database" value="library_system" required>
      <div class="form-text">如不存在，会自动创建。</div></div>
    <div class="col-12">
      <button class="btn btn-primary w-100" type="submit" id="btn">测试连接并保存</button>
    </div>
  </form>
</div>
<script>
const f = document.getElementById('f');
const btn = document.getElementById('btn');
const alertBox = document.getElementById('alert');
f.addEventListener('submit', async (e) => {
  e.preventDefault();
  btn.disabled = true; btn.textContent = '正在测试...';
  alertBox.innerHTML = '';
  const data = Object.fromEntries(new FormData(f));
  try {
    const r = await fetch('/save', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
    const j = await r.json();
    if (j.ok) {
      alertBox.innerHTML = '<div class="alert alert-success">配置成功，正在启动应用…</div>';
      setTimeout(() => window.pywebview.api.finish(), 700);
    } else {
      alertBox.innerHTML = '<div class="alert alert-danger">连接失败：' + j.error + '</div>';
      btn.disabled = false; btn.textContent = '测试连接并保存';
    }
  } catch (err) {
    alertBox.innerHTML = '<div class="alert alert-danger">请求失败：' + err + '</div>';
    btn.disabled = false; btn.textContent = '测试连接并保存';
  }
});
</script>
</body></html>"""


def make_setup_app():
    from flask import Flask, request, jsonify
    app = Flask(__name__)

    @app.route("/")
    def index():
        return SETUP_HTML

    @app.post("/save")
    def save():
        data = request.get_json(force=True)
        cfg = {
            "host": (data.get("host") or "localhost").strip(),
            "port": int(data.get("port") or 3306),
            "user": (data.get("user") or "root").strip(),
            "password": data.get("password") or "",
            "database": (data.get("database") or "library_system").strip(),
            "secret_key": secrets.token_hex(32),
        }
        try:
            ensure_database(cfg)
        except Exception as e:
            return jsonify(ok=False, error=str(e))
        save_config(cfg)
        return jsonify(ok=True)

    return app


class WizardAPI:
    """Exposed to JS via pywebview as window.pywebview.api."""

    def __init__(self):
        self.saved = False

    def finish(self):
        self.saved = True
        for w in list(webview.windows):
            try:
                w.destroy()
            except Exception:
                pass


def run_setup_wizard() -> dict | None:
    flask_app = make_setup_app()
    port = find_free_port()
    server = run_server_in_thread(flask_app, port)
    api = WizardAPI()
    webview.create_window(
        "Personal Library · 首次配置",
        f"http://127.0.0.1:{port}/",
        width=520,
        height=620,
        js_api=api,
    )
    webview.start()
    server.shutdown()
    return load_config() if api.saved else None


def run_main_app(cfg: dict) -> None:
    try:
        ensure_database(cfg)
    except Exception as e:
        sys.stderr.write(f"无法连接 MySQL：{e}\n")
        sys.exit(1)
    flask_app = make_main_app(cfg)
    port = find_free_port()
    server = run_server_in_thread(flask_app, port)
    webview.create_window(
        WINDOW_TITLE,
        f"http://127.0.0.1:{port}/",
        width=1280,
        height=820,
    )
    webview.start()
    server.shutdown()


def main():
    cfg = load_config()
    if cfg is None:
        cfg = run_setup_wizard()
        if cfg is None:
            return
    run_main_app(cfg)


if __name__ == "__main__":
    main()
