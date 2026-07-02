# Concrete Workspace Standard

## 1. Purpose

Define a deterministic dependency workflow for Databricks workloads while using serverless where possible.

## 2. Scope

- Interactive notebooks
- Lakeflow Jobs
- Lakeflow Pipelines

## 3. Dependency Governance

### 3.1 Source of Truth

- `pyproject.toml` defines intended dependencies.
- `uv.lock` pins exact versions.

### 3.2 Runtime Artifact

- `requirements/requirements-standard.txt` is the deployment artifact consumed by Databricks runtime environments.
- This file is generated only by script, not edited manually.

### 3.3 Update Flow

1. Modify `pyproject.toml`.
2. Run `setup_python_env.bat`.
3. Or run `scripts/export_requirements.bat` if only refreshing requirements.
4. Commit all changed files together.

## 4. Interactive Notebook Standard

Use the shared bootstrap entrypoint in notebook cell 1:

```python
# Databricks notebook source
%run /Workspace/Shared/bootstrap/00_bootstrap_env
```

The bootstrap script should:
- Install from `requirements-standard.txt` when needed.
- Skip reinstall when versions already match.
- Print a short summary of what changed.

## 5. Jobs Standard

Every serverless job task must reference an `environment_key`, and every job defines matching `environments` with dependencies from the shared requirements artifact.

## 6. Pipelines Standard

Every serverless pipeline must reference the same shared requirements artifact in the pipeline environment dependencies.

## 7. CI Enforcement

CI must fail when exported requirements are stale relative to `uv.lock`.

Required CI checks:
- `uv lock --check`
- Regenerate requirements in a temp path
- Compare generated output to `requirements/requirements-standard.txt`

## 8. Ownership

- Platform team owns templates and CI policy.
- Feature teams can add package dependencies only through `pyproject.toml`.

## 9. Exceptions

If a package is not compatible with serverless constraints, raise a platform exception and isolate that workload to non-serverless governed compute.
