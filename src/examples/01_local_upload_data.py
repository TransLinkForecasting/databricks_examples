import csv
import subprocess
from datetime import datetime
from pathlib import Path


VOLUME_DIR = "dbfs:/Volumes/forecasting_dev/learning/files/examples"


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{result.stdout}\n{result.stderr}")


def _get_username() -> str:
    result = subprocess.run(["whoami"], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Unable to get username via whoami: {result.stderr}")
    return result.stdout.strip()


def main() -> None:
    now = datetime.now()
    filename_stamp = now.strftime("%Y%m%d%H%M")
    row_timestamp = now.strftime("%Y-%m-%d %H:%M")
    username = _get_username()

    local_examples = Path("examples")
    local_examples.mkdir(parents=True, exist_ok=True)

    local_file = local_examples / f"hello_world_{filename_stamp}.csv"
    with local_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["TimeStamp", "UserName"])
        writer.writerow([row_timestamp, username])

    remote_file = f"{VOLUME_DIR}/hello_world_{filename_stamp}.csv"

    _run(["databricks", "fs", "mkdirs", VOLUME_DIR])
    _run(["databricks", "fs", "cp", str(local_file), remote_file, "--overwrite"])

    print(f"Generated local file: {local_file}")
    print(f"Uploaded file to: {remote_file}")


if __name__ == "__main__":
    main()
