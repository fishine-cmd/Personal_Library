# PyInstaller spec for Personal Library desktop app.
# Build with:  pyinstaller library_system.spec
# Output:      dist/PersonalLibrary/PersonalLibrary.exe (+ supporting files)

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

datas = [
    ("app/templates", "app/templates"),
    ("app/static", "app/static"),
]
binaries = []
hiddenimports = [
    "pymysql",
    "flask_sqlalchemy",
    "flask_login",
    "bibtexparser",
    "email_validator",
    "werkzeug.security",
    "sqlalchemy.dialects.mysql",
    # MinerU integration HTTP client
    "requests",
    "urllib3",
    "charset_normalizer",
    "idna",
    "certifi",
]

# Pull in all submodules of our own app package (blueprints/services are
# imported lazily inside the Flask factory, so PyInstaller's static
# analyzer can't see them on its own).
hiddenimports += collect_submodules("app")

# pythonnet + clr_loader are needed by pywebview on Windows to embed WebView2
# via .NET; without their data files the loader fails at startup.
for pkg in ("pythonnet", "clr_loader", "webview"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

excludes = [
    "pytest",
    "tkinter",
]

a = Analysis(
    ["desktop_app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PersonalLibrary",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PersonalLibrary",
)
