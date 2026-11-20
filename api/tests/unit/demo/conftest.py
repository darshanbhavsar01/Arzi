import sys
from pathlib import Path

# The generator lives in scripts/ (it is tooling, not product code); make it importable.
SCRIPTS = Path(__file__).resolve().parents[4] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
