import argparse
from pyspark.sql import SparkSession
from pyspark.sql import functions as F


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read latest hello world CSV from Unity Catalog Volumes.")
    parser.add_argument(
        "--examples-dir",
        default="/Volumes/forecasting_dev/learning/files/examples",
        help="Directory containing hello_world_YYYYMMDDHHMM.csv files.",
    )
    return parser.parse_args()


def _normalize_volume_dir(path: str) -> str:
    # Keep Unity Catalog volume path format stable across OS shells.
    return path.replace("\\", "/").rstrip("/")


def _latest_row_from_volume(spark: SparkSession, examples_dir: str):
    pattern = f"{examples_dir}/hello_world_*.csv"
    try:
        df = spark.read.option("header", True).csv(pattern)
    except Exception as exc:
        raise FileNotFoundError(f"No hello_world_*.csv files found in {examples_dir}") from exc

    # Spark Connect does not implement DataFrame.rdd; use limit/collect instead.
    sample = df.limit(1).collect()
    if not sample:
        raise FileNotFoundError(f"No hello_world_*.csv files found in {examples_dir}")

    latest = (
        df.withColumn("_file", F.col("_metadata.file_path"))
        .orderBy(F.col("_file").desc())
        .limit(1)
        .collect()[0]
    )
    return latest


def main() -> None:
    args = parse_args()
    examples_dir = _normalize_volume_dir(args.examples_dir)

    spark = SparkSession.builder.getOrCreate()
    latest = _latest_row_from_volume(spark, examples_dir)

    print(f"Reading latest file from: {examples_dir}")
    print(f"TimeStamp: {latest['TimeStamp']}")
    print(f"UserName: {latest['UserName']}")

    print("hello world")


if __name__ == "__main__":
    main()
