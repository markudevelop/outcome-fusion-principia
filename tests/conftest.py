"""Make the plugin's hook scripts importable as top-level modules in tests."""
import pathlib
import sys

SCRIPTS = (
    pathlib.Path(__file__).resolve().parent.parent
    / "plugins"
    / "outcome-fusion-principia"
    / "scripts"
)
sys.path.insert(0, str(SCRIPTS))
