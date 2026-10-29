import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))   # for set_password helpers

# Pin "today" to the seed's reference date so tests are deterministic.
os.environ.setdefault("HRIS_TODAY", "2026-10-28")
