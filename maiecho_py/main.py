import importlib
from pathlib import Path
import sys

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def main() -> None:
    module = importlib.import_module("maiecho_py.cmd.maiecho.main")
    entrypoint = getattr(module, "main")
    entrypoint()


if __name__ == "__main__":
    main()
