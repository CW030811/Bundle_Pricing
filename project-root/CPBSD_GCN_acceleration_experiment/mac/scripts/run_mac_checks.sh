#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "[1/3] Python version"
python3 -V

echo "[2/3] Import checks"
python3 - <<'PY'
mods=['numpy','pandas','torch','torch_geometric','gurobipy','msgpack','msgpack_numpy']
for m in mods:
    try:
        __import__(m)
        print('OK',m)
    except Exception as e:
        print('MISS',m,e)
PY

echo "[3/3] Path check"
python3 - <<'PY'
from pathlib import Path
root=Path('.').resolve()
print('ROOT=',root)
for p in ['src/data/generate_data_MB.py','src/data/generate_data_BSP.py','src/train/Training_edge-final.py','src/test/test_FCP.py','src/test/test_PCP.py']:
    print(p, (root/p).exists())
PY

echo "Done."
