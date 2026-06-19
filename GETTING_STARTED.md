# Getting Started

This guide covers the shortest path to run the hello world examples (job + pipeline).

## 1. Run Scripts Locally

### Prerequisites

- Windows machine with internet access.
- Git clone of this repository.

### Databricks CLI Source

Assume Databricks CLI is provided by the VS Code Databricks extension:

https://marketplace.visualstudio.com/items?itemName=databricks.databricks

Verify installation:

```bat
databricks -v
```

Authenticate to your workspace:

```bat
databricks auth login --host https://<your-databricks-workspace-host>
```

You do not need a global `uv` installation. This project bootstraps `uv` into `.uv`.

### Initial setup

From repository root:

```bat
run_python_cmds.bat
```

This command bootstraps `.uv`, `.venv`, syncs dependencies, updates `uv.lock`, and exports `requirements/requirements-standard.txt`.

To include a model group, pass `--group` explicitly:

```bat
run_python_cmds.bat --group activitysim
run_python_cmds.bat --group populationsim
```

### Run local Python commands

```bat
run_python_cmds.bat -c "import tlpytools; print('ok')"
run_python_cmds.bat --group activitysim -c "print('using activitysim group')"
run_python_cmds.bat --group populationsim -c "print('using populationsim group')"
```

### Refresh requirements artifact only

```bat
scripts\export_requirements.bat
```

### Verify requirements are in sync with `uv.lock`

```bat
scripts\check_requirements_drift.bat
```

## 2. Run in Databricks (Job + Pipeline)

From repository root:

```bat
databricks bundle validate --target dev
databricks bundle deploy --target dev
```

## Hello World Example

This example flow:
1. Generate and upload a CSV file locally.
2. Run a serverless Databricks job.
3. Run a serverless Databricks pipeline that creates a table from uploaded CSV files.

### Files used

- Local step script: `src/examples/01_local_upload_data.py`
- Databricks step script: `src/examples/02_databrick_hello_world.py`
- Pipeline SQL source: `src/examples/hello_world_pipeline.sql`
- Job resource: `resources/jobs/hello_world_example.job.yml`
- Pipeline resource: `resources/pipelines/hello_world_example.pipeline.yml`

### Step 1: Generate and upload hello world CSV locally

Run this from repository root (this is local only):

```bat
run_python_cmds.bat src\examples\01_local_upload_data.py
```

What this does:
1. Runs `whoami` to get the current user.
2. Generates a CSV file in `examples/` with this format:

```text
TimeStamp,UserName
<current local datetime>,<whoami output>
```

3. Uses a datetime-stamped filename:

```text
hello_world_YYYYMMDDHHMM.csv
```

4. Uploads it to Unity Catalog Volumes:

```text
dbfs:/Volumes/forecasting_dev/learning/files/examples/hello_world_YYYYMMDDHHMM.csv
```

### Step 2: Run hello world on Databricks

Validate and deploy bundle:

```bat
databricks bundle validate --target dev
databricks bundle deploy --target dev
```

Run the hello world job:

```bat
databricks bundle run hello_world_example --target dev
```

Run the hello world pipeline:

```bat
databricks bundle run hello_world_example_pipeline --target dev
```

Expected behavior:
1. Job prints latest CSV metadata and `hello world`.
2. Pipeline creates/updates `forecasting_dev.learning.hello_world_example_table`.

## Recommended Team Workflow

1. Run local setup (`run_python_cmds.bat`).
2. Generate/upload test CSV (`src/examples/01_local_upload_data.py`).
3. Deploy bundle and run job/pipeline examples.
4. Keep `requirements/requirements-standard.txt` and `uv.lock` in sync.

## Notes

- Python support is constrained in `pyproject.toml` to `>=3.12,<3.13`.
- As of June 2026, `activitysim` cannot be set up as part of this Python 3.12 environment because it requires `numpy<1.26`, which is not supported in this setup.
- If you need `activitysim`, use a separate Python 3.11 environment dedicated to that workflow.
- Job and pipeline examples both consume `requirements/requirements-standard.txt` so runtime dependencies stay aligned.
