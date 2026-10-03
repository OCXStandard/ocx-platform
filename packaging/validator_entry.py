"""PyInstaller entry point for the standalone validator executable.

Build (from the repo root):

    uv run pyinstaller packaging/validator.spec --noconfirm

The resulting single-file executable lands in ``dist/ocx-validator.exe``
and runs on Windows machines without a Python installation.
"""
from ocx_model_validator.cli import entrypoint

if __name__ == "__main__":
    entrypoint()
