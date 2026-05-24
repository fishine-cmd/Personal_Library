# 激活虚拟环境
.\.venv\Scripts\Activate.ps1

# 安装依赖
pip install -r requirements-build.txt

# 打包程序
pyinstaller library_system.spec --clean --noconfirm

# 结束提示
Write-Host "`ndown" -ForegroundColor Green
pause