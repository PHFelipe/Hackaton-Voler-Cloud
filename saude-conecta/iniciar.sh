#!/usr/bin/env sh
# Linux/macOS: ./iniciar.sh   (ou ./iniciar.sh testes)
cd "$(dirname "$0")"
for py in python3.13 python3.12 python3.11 python3 python; do
  if command -v "$py" >/dev/null 2>&1 && "$py" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
    exec "$py" run.py "$@"
  fi
done
echo "Instale o Python 3.11 ou mais novo: https://www.python.org/downloads/"
exit 1
