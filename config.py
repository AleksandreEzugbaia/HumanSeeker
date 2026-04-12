"""
Path configuration: works both from source and when frozen by PyInstaller.
"""

import os
import sys


def _base_dir():
    if getattr(sys, "frozen", False):
        # Running as a PyInstaller bundle: .exe directory for user data
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _internal_dir():
    if getattr(sys, "frozen", False):
        # PyInstaller puts bundled data files in _MEIPASS (the _internal dir)
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = _base_dir()
INTERNAL_DIR = _internal_dir()

# Frontend and backend code live inside the bundle (_internal/) when frozen
FRONTEND_DIR = os.path.join(INTERNAL_DIR, "frontend")
BACKEND_DIR = os.path.join(INTERNAL_DIR, "backend")

# User data lives next to the .exe so it persists across runs
BASELINES_DIR = os.path.join(BASE_DIR, "baselines")
ENV_PATH = os.path.join(BASE_DIR, ".env")
