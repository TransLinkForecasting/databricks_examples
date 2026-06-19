# Getting Started

This guide explains how to use this environment in 3 main ways:
1. Run scripts locally to test that everything works.
2. Run scripts in Databricks Jobs on larger datasets and read/write from Unity Catalog `forecasting_dev`.
3. Set up and run Databricks notebooks with the same dependency baseline.

## 1. Run Scripts Locally

### Prerequisites

- Windows machine with internet access.
- Git clone of this repository.

### Install Databricks CLI (Windows)

Install using one of the following methods.

#### Option A: winget (recommended)

```bat
winget install Databricks.DatabricksCLI
```

#### Option B: Chocolatey

```bat
choco install databricks-cli -y
```

#### Option C: pipx (if package managers are unavailable)

```bat
pip install pipx
pipx ensurepath
pipx install databricks-cli
```

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

This command does the full setup:
- Downloads `uv` into `.uv` (project-local).
- Creates `.venv`.
- Installs dependencies, including:
  - `tlpytools[dev,orca]`
  - dependency group `dev` (default)
- Creates/updates `uv.lock`.
- Exports `requirements/requirements-standard.txt`.

To include a model group, pass `--group` explicitly:

```bat
run_python_cmds.bat --group activitysim
run_python_cmds.bat --group populationsim
```

### Run local Python commands

```bat
run_python_cmds.bat -c "import tlpytools; print('ok')"
run_python_cmds.bat src\examples\main.py
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

## 2. Run in Databricks Jobs (Large Datasets)

This repo already includes a serverless job template at `resources/jobs/serverless_job_template.yml` and bundle config in `databricks.yml`.

### Step A: Configure bundle target

1. Confirm workspace host in `databricks.yml`.
2. Authenticate Databricks CLI if needed:

```bat
databricks auth login --host https://<your-databricks-workspace-host>
```

### Step B: Deploy and run job

From repository root:

```bat
databricks bundle validate --target dev
databricks bundle deploy --target dev
databricks bundle run standard_serverless_python_job --target dev
```

### Step C: Where to drop files in Unity Catalog `forecasting_dev`

Use Unity Catalog Volumes for file-style inputs/outputs.

Recommended path pattern:

```text
/Volumes/forecasting_dev/<schema>/<volume>/input/
/Volumes/forecasting_dev/<schema>/<volume>/output/
```

Example:

```text
/Volumes/forecasting_dev/demand_forecasting/raw_files/input/trips_2026_06.parquet
```

You can upload files by:
1. Databricks UI: Catalog > `forecasting_dev` > schema > volume > Upload.
2. Databricks CLI (example):

```bat
databricks fs cp "C:\data\trips_2026_06.parquet" "dbfs:/Volumes/forecasting_dev/demand_forecasting/raw_files/input/trips_2026_06.parquet"
```

### Step D: How to reference `forecasting_dev` data in code

#### File-based (volume paths)

```python
input_path = "/Volumes/forecasting_dev/demand_forecasting/raw_files/input/trips_2026_06.parquet"
output_path = "/Volumes/forecasting_dev/demand_forecasting/raw_files/output/forecast_2026_06.parquet"

spark.read.parquet(input_path)
```

#### Table-based (Unity Catalog tables)

```python
df = spark.table("forecasting_dev.demand_forecasting.trip_facts")
```

Use table names as:

```text
<catalog>.<schema>.<table>
```

For this catalog:

```text
forecasting_dev.<schema>.<table>
```

## 3. Set Up and Run Databricks Notebook

Use notebooks for exploratory and interactive workflows while keeping dependencies aligned.

### Step A: Create notebook

Create a notebook in Databricks workspace and attach serverless compute.

### Step B: Bootstrap dependencies in first cell

In cell 1, run the shared bootstrap:

```python
%run /Workspace/Shared/bootstrap/00_bootstrap_env
```

This bootstrap script is maintained in this repo at:
- `notebooks/bootstrap/00_bootstrap_env.py`

Make sure your workspace copy of `/Workspace/Shared/bootstrap/00_bootstrap_env` is updated from this repository version.

### Step C: Access `forecasting_dev` files/tables

Notebook examples:

```python
# File from UC Volume
path = "/Volumes/forecasting_dev/demand_forecasting/raw_files/input/trips_2026_06.parquet"
df_files = spark.read.parquet(path)

# Table from UC
trip_df = spark.table("forecasting_dev.demand_forecasting.trip_facts")
```

### Step D: Promote notebook logic to Jobs

After notebook logic is validated:
1. Move reusable logic into Python scripts under `src/`.
2. Point job task entrypoint to that script in `resources/jobs/serverless_job_template.yml`.
3. Deploy and run with `databricks bundle deploy` and `databricks bundle run`.

## Hello World Example

This example shows a complete flow in this repository:
1. Generate and upload a CSV file locally.
2. Run a serverless Databricks job that reads the latest uploaded file.
3. Print the CSV content and then print `hello world`.

### Files used

- Local step script: `src/examples/01_local_upload_data.py`
- Databricks step script: `src/examples/02_databrick_hello_world.py`
- Job resource: `resources/jobs/hello_world_example.job.yml`

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

Expected Databricks script behavior:
1. Finds latest `hello_world_*.csv` under `/Volumes/forecasting_dev/learning/files/examples`
2. Prints the file content.
3. Prints `hello world`.

## Recommended Team Workflow

1. Develop and test locally first (`run_python_cmds.bat`).
2. Validate with notebook on sample data in `forecasting_dev`.
3. Run production-scale workloads via bundle-managed Jobs.
4. Keep `requirements/requirements-standard.txt` and `uv.lock` in sync.

## Notes

- Python support is constrained in `pyproject.toml` to `>=3.12,<3.13`.
- As of June 2026, `activitysim` cannot be set up as part of this Python 3.12 environment because it requires `numpy<1.26`, which is not supported in this setup.
- If you need `activitysim`, use a separate Python 3.11 environment dedicated to that workflow.
- Job and pipeline templates both consume `requirements/requirements-standard.txt` so runtime dependencies stay aligned.
