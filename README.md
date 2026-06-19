# Databricks Workspace Standard (Serverless + uv)

Minimal Databricks bundle workspace with a single example:
1. `hello_world_example` job
2. `hello_world_example_pipeline` pipeline

## Quick Setup

```bat
run_python_cmds.bat
```

Optional model groups:

```bat
run_python_cmds.bat --group activitysim
run_python_cmds.bat --group populationsim
```

## Hello World Run

Generate and upload example CSV:

```bat
run_python_cmds.bat src\examples\01_local_upload_data.py
```

Deploy and run resources:

```bat
databricks bundle validate --target dev
databricks bundle deploy --target dev
databricks bundle run hello_world_example --target dev
databricks bundle run hello_world_example_pipeline --target dev
```

## Notebook Walkthrough

Use `notebooks/hello-world.ipynb` to run the same example interactively.

1. In Databricks workspace, upload/open `notebooks/hello-world.ipynb`.
2. Make sure these files exist in workspace paths used by the notebook:
	- `/Workspace/Shared/bootstrap/00_bootstrap_env`
	- `/Workspace/Shared/dependencies/requirements-standard.txt`
3. Attach serverless compute.
4. Run Cell 1 (instructions), then Cell 2 (bootstrap), then Cell 3 (read latest CSV + print hello world).

Tip: run local upload first so the notebook has data to read:

```bat
run_python_cmds.bat src\examples\01_local_upload_data.py
```

## Key Files

- `requirements/requirements-standard.txt`
- `resources/jobs/hello_world_example.job.yml`
- `resources/pipelines/hello_world_example.pipeline.yml`
- `src/examples/01_local_upload_data.py`
- `src/examples/02_databrick_hello_world.py`
- `src/examples/hello_world_pipeline.sql`
- `notebooks/hello-world.ipynb`
- `notebooks/bootstrap/00_bootstrap_env.py`
