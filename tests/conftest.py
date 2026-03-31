import sys
from pathlib import Path

# Make scripts/ importable as a flat namespace (e.g. `from analytics import ...`)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
