@echo off
:: 关闭占用 8000 端口的进程
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
)
:: 等待端口释放
timeout /t 2 /nobreak >nul
:: 启动服务
start http://localhost:8000
python3 web_app.py