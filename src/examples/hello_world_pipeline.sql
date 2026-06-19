CREATE OR REFRESH MATERIALIZED VIEW hello_world_example_table
AS
SELECT
  TimeStamp,
  UserName,
  _metadata.file_path AS source_file
FROM read_files(
  '/Volumes/forecasting_dev/learning/files/examples/hello_world_*.csv',
  format => 'csv',
  header => 'true'
);
