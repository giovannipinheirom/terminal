#!/usr/bin/env bash
# Mac / Linux:  bash iniciar_laboratorio.sh
cd "$(dirname "$0")" || exit 1
export PYTHONIOENCODING=utf-8

PY="$(command -v python3 || command -v python)"
if [ -z "$PY" ]; then
    echo "Python não encontrado. Instale o Python 3.10+ (https://www.python.org/downloads/)."
    exit 1
fi
if ! "$PY" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
    echo "Seu Python é antigo ($("$PY" --version)). Precisa do 3.10 ou mais novo."
    exit 1
fi

echo "Iniciando o laboratório... painel em http://127.0.0.1:8765  (Ctrl+C para parar)"
exec "$PY" -m lab
