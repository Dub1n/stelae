#!/usr/bin/env bash
set -euo pipefail

VENV="${HOME}/.venvs/stelae-bridge"
PY="${VENV}/bin/python"
REQ="${HOME}/dev/stelae/bridge/requirements.txt"

# create venv if missing
if [ ! -x "${PY}" ]; then
  python3 -m venv "${VENV}"
fi

# install/upgrade deps inside the venv
"${PY}" -m pip install --upgrade pip
"${PY}" -m pip install -r "${REQ}"

# print the python path for pm2 env
echo "BRIDGE_PY=${PY}"
