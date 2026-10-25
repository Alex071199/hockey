#!/bin/bash
# Деплой backend на alwaysdata (запускать по SSH после загрузки кода)
set -e

cd /home/$USER/backend

echo "=== Установка зависимостей ==="
/usr/bin/python -m pip install --user -r requirements.txt

echo "=== Готово ==="
echo "Теперь в админке alwaysdata:"
echo "1. Web > Sites > Add site"
echo "2. Type: User program (ASGI)"
echo "3. Command: uvicorn app.main:app --host \$IP --port \$PORT --workers 1"
echo "4. Working directory: /home/$USER/backend"
echo "5. Environment variables:"
echo "   TURSO_DATABASE_URL=libsql://hockey-alex071199.aws-eu-north-1.turso.io"
echo "   TURSO_AUTH_TOKEN=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9..."
echo "   PUBLIC_API_URL=https://$USER.alwaysdata.com"
echo "   PYTHON_VERSION=3.11"
