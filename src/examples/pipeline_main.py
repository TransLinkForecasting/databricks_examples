# Databricks notebook source
import dlt
from pyspark.sql import functions as F


@dlt.table(
	name="hello_world_example_table",
	comment="Reads uploaded hello_world CSV files from Unity Catalog Volume.",
)
def hello_world_example_table():
	path_pattern = "/Volumes/forecasting_dev/learning/files/examples/hello_world_*.csv"
	return (
		spark.read.option("header", True)
		.csv(path_pattern)
		.withColumn("source_file", F.col("_metadata.file_path"))
	)
