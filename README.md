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

## Key Files

- `requirements/requirements-standard.txt`
- `resources/jobs/hello_world_example.job.yml`
- `resources/pipelines/hello_world_example.pipeline.yml`
- `src/examples/01_local_upload_data.py`
- `src/examples/02_databrick_hello_world.py`
- `src/examples/hello_world_pipeline.sql`
- `notebooks/bootstrap/00_bootstrap_env.py`
