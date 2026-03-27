from __future__ import annotations

import sys
from pathlib import Path

PACKAGE_SRC = Path(__file__).resolve().parents[1] / "src"

if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from shared_schemas.schema_export import write_schema_bundle


if __name__ == "__main__":
    output_dir = Path(__file__).resolve().parents[1] / "schemas"
    path = write_schema_bundle(output_dir)
    print(path)
