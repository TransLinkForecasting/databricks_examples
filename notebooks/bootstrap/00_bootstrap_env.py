# Databricks notebook source
"""
Shared bootstrap for interactive notebooks.

Usage in notebook cell 1:
%run /Workspace/Shared/bootstrap/00_bootstrap_env
"""

import os
import sys
import subprocess
from pathlib import Path


def _find_requirements_file() -> str:
    candidates = [
        "/Workspace/Shared/dependencies/requirements-serverless.txt",
        "requirements/requirements-serverless.txt",
        "../requirements/requirements-serverless.txt",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return candidates[0]


def install_shared_dependencies(requirements_path: str | None = None) -> None:
    req = requirements_path or _find_requirements_file()
    print(f"[bootstrap] Installing dependencies from: {req}")

    cmd = [sys.executable, "-m", "pip", "install", "-r", req]

    # In ephemeral serverless environments, idempotent installs are expected.
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        raise RuntimeError("Dependency bootstrap failed")

    print("[bootstrap] Dependency bootstrap completed")


if os.environ.get("SKIP_NOTEBOOK_BOOTSTRAP", "0") != "1":
    install_shared_dependencies()
