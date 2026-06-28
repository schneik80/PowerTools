"""Pytest configuration for the PowerTools add-in test suite.

These tests run OUTSIDE Fusion, where the ``adsk`` API package does not exist.
Two pieces of scaffolding make the add-in importable under test:

1. The repository root is placed on ``sys.path`` so add-in modules resolve.
2. Lightweight stub modules for ``adsk``, ``adsk.core`` and ``adsk.fusion`` are
   installed into ``sys.modules`` before collection, so any module that does
   ``import adsk.*`` (or calls ``adsk.core.Application.get()``) at load time can
   be imported. The stubs use ``MagicMock`` so arbitrary attribute access does
   not raise; no real Fusion behavior is exercised — tests target pure logic.

Pure-logic helpers with no Fusion dependency (e.g.
``lib/ptAddInUtils/json_utils.py``) need none of this and are imported directly
by their own tests.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Install stub Fusion modules so add-in imports don't fail outside Fusion.
for _adsk_module in ("adsk", "adsk.core", "adsk.fusion"):
    sys.modules.setdefault(_adsk_module, MagicMock(name=_adsk_module))
