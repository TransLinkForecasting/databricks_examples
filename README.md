# Databricks Workspace Standard (Serverless + uv)

This repository defines a concrete standard for keeping Python dependencies aligned across:
- Interactive notebooks
- Lakeflow Jobs (serverless)
- Lakeflow Pipelines (serverless)

The design goal is consistent behavior without requiring users to manually install packages in every notebook.

## Core Principles

1. Single dependency source of truth: `pyproject.toml` + `uv.lock`.
2. Runtime artifact: export pinned dependencies to `requirements/requirements-standard.txt`.
3. Reuse the same artifact in jobs and pipelines.
4. Provide one shared notebook bootstrap helper for interactive sessions.
5. Enforce drift checks in CI.

## Current Environment Standard

1. Python compatibility is constrained to `>=3.12,<3.13`.
2. Base dependencies include `tlpytools[dev,orca]`.
3. Additional dependency groups are enabled:
	- `dev`
	- `activitysim`
  - `populationsim`
4. `run_python_cmds.bat` is the single entrypoint for setup and Python command execution.

## One-Command Setup (Windows CMD)

Run from repository root:

```bat
run_python_cmds.bat
```

This command will:
1. Download project-local `uv` into `.uv` (if not already present).
2. Create `.venv` (if not already present).
3. Activate `.venv` for the script session.
4. Run `uv sync --group dev`.
5. Refresh `uv.lock`.
6. Export `requirements/requirements-standard.txt`.

By default, no model group is selected (`activitysim` and `populationsim` are not included).
Use a model group explicitly:

```bat
run_python_cmds.bat --group activitysim
run_python_cmds.bat --group populationsim
```

## Run Python Commands Through the Entrypoint

```bat
run_python_cmds.bat -c "print('hello')"
run_python_cmds.bat path\to\script.py
run_python_cmds.bat --group populationsim -c "print('population sim env')"
```

This guarantees the project-local `.uv` and `.venv` are used.

## Quick Start

1. Run `run_python_cmds.bat` from the repo root.
2. Update dependencies in `pyproject.toml`.
3. Re-run `run_python_cmds.bat`.
4. If only requirements export is needed, run `scripts\\export_requirements.bat`.
4. Reference `requirements/requirements-standard.txt` in bundle resources.
5. For notebooks, run the bootstrap helper from `notebooks/bootstrap/00_bootstrap_env.py`.

## Dependency Maintenance Commands

```bat
scripts\export_requirements.bat
scripts\check_requirements_drift.bat
```

- `export_requirements.bat`: regenerates `requirements/requirements-standard.txt`.
- `check_requirements_drift.bat`: fails if exported requirements are stale versus `uv.lock`.

## Repository Layout

- `docs/workspace-standard.md`: Full operating standard.
- `run_python_cmds.bat`: Entrypoint to bootstrap uv, `.venv`, lock, and exports.
- `scripts/export_requirements.bat`: Exports pinned requirements from uv lock.
- `scripts/check_requirements_drift.bat`: Fails if lock export is stale.
- `requirements/requirements-standard.txt`: Runtime dependency artifact.
- `resources/jobs/hello_world_example.job.yml`: Hello world job example.
- `resources/pipelines/hello_world_example.pipeline.yml`: Hello world pipeline example.
- `notebooks/bootstrap/00_bootstrap_env.py`: Shared notebook bootstrap entrypoint.
- `.github/workflows/validate-dependency-alignment.yml`: CI enforcement.
