"""Pytest configuration for the PowerTools add-in test suite.

These tests run OUTSIDE Fusion, where the ``adsk`` API package does not exist.
Two pieces of scaffolding make the add-in importable under test:

1. The add-in root is pre-registered in ``sys.modules`` as a package
   (``PowerTools``) whose ``__path__`` is the repository root. This lets modules
   that use relative imports (``from ... import config``) be imported in tests as
   ``PowerTools.<module>`` / ``PowerTools.commands.<cmd>.entry`` — the same
   package name Fusion loads the add-in under. Pre-registering it avoids a name
   collision: the repo root also contains ``PowerTools.py`` (the add-in entry
   module), which would otherwise shadow the ``PowerTools/`` package directory
   whenever the repo root is on ``sys.path`` (e.g. ``python -m pytest`` puts the
   cwd there).
2. A meta-path finder fabricates any ``adsk`` / ``adsk.*`` module on demand as a
   ``MagicMock`` package. This covers arbitrary submodule imports (``adsk.core``,
   ``adsk.fusion``, ``adsk.cam``, ...) and attribute access such as
   ``adsk.core.Application.get()`` without exercising any real Fusion behavior —
   tests target pure logic only.

Pure-logic helpers with no Fusion dependency (e.g.
``lib/ptAddInUtils/json_utils.py``) need none of this and are imported directly
from their file path by their own tests.
"""

import importlib.abc
import importlib.machinery
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parent.parent
# Package name Fusion loads the add-in under (the add-in folder name).
PT_PKG = REPO_ROOT.name

# Pre-register the add-in root as a package rooted at the repo directory.
if PT_PKG not in sys.modules:
    _root = types.ModuleType(PT_PKG)
    _root.__path__ = [str(REPO_ROOT)]
    _root.__package__ = PT_PKG
    sys.modules[PT_PKG] = _root


class _AdskStubFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Fabricate any ``adsk`` / ``adsk.*`` module as a MagicMock package.

    Registered on ``sys.meta_path`` so it is consulted only for names not
    already imported; anything under the ``adsk`` namespace resolves to a mock
    that behaves as both a module and a package (``__path__`` set) so nested
    submodule imports succeed.
    """

    def find_spec(self, fullname, path, target=None):
        if fullname == "adsk" or fullname.startswith("adsk."):
            return importlib.machinery.ModuleSpec(fullname, self)
        return None

    def create_module(self, spec):
        module = MagicMock(name=spec.name)
        module.__path__ = []  # mark as a package so ``import adsk.x`` proceeds
        return module

    def exec_module(self, module):  # nothing to execute for a stub
        pass


if not any(isinstance(f, _AdskStubFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _AdskStubFinder())
