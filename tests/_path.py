"""Ensure local addon modules are importable during tests."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_ROOT = ROOT / "intelbras_bridge" / "alarme-intelbras"

if str(PROTOCOL_ROOT) not in sys.path:
    sys.path.insert(0, str(PROTOCOL_ROOT))
