"""venv / site-packages detection (decision 02/04).

Separates project code from site-packages so third-party symbols resolve to
``External`` nodes. The classifier uses three signals:

  1. project-local modules  - built by the extractor from the AST (authoritative)
  2. stdlib                 - ``sys.stdlib_module_names`` (3.10+)
  3. everything else        - ``External`` (third-party), optionally confirmed
                              by a site-packages path from the active venv
"""

from __future__ import annotations

import importlib.util
import site as _site
import sys
import sysconfig
from dataclasses import dataclass, field


@dataclass
class VenvInfo:
    project_root: str
    site_packages: list[str] = field(default_factory=list)
    stdlib_path: str = ""

    def is_stdlib(self, top_name: str) -> bool:
        return top_name in sys.stdlib_module_names

    def find_installed_path(self, name: str) -> str | None:
        """Best-effort: where is ``name`` installed, or None if not importable."""
        try:
            spec = importlib.util.find_spec(name)
        except (ModuleNotFoundError, ValueError, ImportError):
            return None
        if spec is None:
            return None
        return getattr(spec, "origin", None) or (spec.submodule_search_locations[0] if spec.submodule_search_locations else None)

    def is_site_packages(self, path: str | None) -> bool:
        if not path:
            return False
        norm = str(path).lower()
        return any(norm.startswith(sp.lower()) for sp in self.site_packages)


def detect(project_root: str) -> VenvInfo:
    """Detect the active environment's site-packages and stdlib paths."""
    sp: list[str] = []
    try:
        sp.extend(_site.getsitepackages())
    except Exception:
        pass
    try:
        u = _site.getusersitepackages()
        if u:
            sp.append(u)
    except Exception:
        pass
    stdlib = sysconfig.get_paths().get("stdlib", "")
    return VenvInfo(project_root=str(project_root), site_packages=sp, stdlib_path=stdlib)


def classify(name: str, project_modules: set[str], venv: VenvInfo) -> str:
    """Classify a top-level import name.

    Returns ``"project"``, ``"stdlib"``, or ``"external"``.
    """
    top = name.split(".")[0]
    if top in project_modules or name in project_modules:
        return "project"
    if venv.is_stdlib(top):
        return "stdlib"
    return "external"
