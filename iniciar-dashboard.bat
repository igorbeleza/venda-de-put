@echo off
REM Sobe o dashboard na porta padrao do projeto (8765); se estiver ocupada,
REM sobe numa porta livre aleatoria. Abre o navegador sozinho.
REM Duplo-clique nesse arquivo. Sem terminal, sem Python na mao.
REM Senha de admin/chave de sessao vem do .env (copie .env.example se ainda nao tiver).

cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"

for /f %%p in ('python scripts\pick_port.py') do set PORT=%%p

echo.
echo   Dashboard venda de PUT
echo   http://127.0.0.1:%PORT%
echo.
echo   O navegador abre sozinho em alguns segundos.
echo   Fica uma janela separada com o titulo da porta rodando o
echo   servidor - feche ela quando quiser parar o dashboard.
echo.

start "Dashboard venda de PUT - porta %PORT%" cmd /k python -m venda_de_put serve --host 127.0.0.1 --port %PORT%

timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:%PORT%"
