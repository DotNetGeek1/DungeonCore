from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
for path in (
    REPO_ROOT / ".codex_deps",
    REPO_ROOT / "packages" / "shared-config" / "src",
    REPO_ROOT / "packages" / "shared-schemas" / "src",
):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from shared_config.settings import ServiceSettings


def test_placeholder() -> None:
    settings = ServiceSettings(service_name="orchestrator", port=8001)
    assert settings.service_name == "orchestrator"
