"""Root conftest.py — ensure Windows DLL search path includes Python installation dir.

On Windows with Python 3.14, the greenlet .pyd extension requires vcruntime140.dll
which lives in the Python installation directory. Python 3.8+ provides
os.add_dll_directory() to add it to the search path before any extension is imported.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _add_python_dll_dirs() -> None:
    """Add Python installation DLL directories to Windows DLL search path."""
    if sys.platform != "win32":
        return
    if not hasattr(os, "add_dll_directory"):
        return  # Python < 3.8

    python_dir = Path(sys.executable).parent
    # Walk up looking for vcruntime140.dll
    for parent in [python_dir, python_dir.parent]:
        if (parent / "vcruntime140.dll").exists():
            try:
                os.add_dll_directory(str(parent))
            except (OSError, ValueError):
                pass

    # Add greenlet package directory — on Python 3.14/Windows, greenlet's .pyd
    # requires MSVCP140.dll and api-ms-win-crt-*.dll which we copy there.
    import site
    for site_dir in site.getsitepackages():
        glet_dir = Path(site_dir) / "greenlet"
        if glet_dir.is_dir() and (glet_dir / "MSVCP140.dll").exists():
            try:
                os.add_dll_directory(str(glet_dir))
            except (OSError, ValueError):
                pass

    # Also add the standard system dirs just in case
    for d in os.environ.get("PATH", "").split(os.pathsep):
        if d and Path(d).is_dir() and any(
            (Path(d) / dll).exists()
            for dll in ("vcruntime140.dll", "python3.dll")
        ):
            try:
                os.add_dll_directory(d)
            except (OSError, ValueError):
                pass


_add_python_dll_dirs()
