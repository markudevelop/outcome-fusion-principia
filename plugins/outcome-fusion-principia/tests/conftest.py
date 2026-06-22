"""Make the plugin's hook scripts importable as top-level modules in tests."""
import pathlib
import sys

# tests/ lives inside the plugin folder, alongside scripts/.
SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
