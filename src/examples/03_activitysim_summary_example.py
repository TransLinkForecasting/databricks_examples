"""Summarize ActivitySim outputs: cross-iteration mode share + a detailed profile.

Part 1 (all iterations): trip/tour mode shares per iteration, an iteration pivot,
and iter1->4 change tables. This is the original analysis, unchanged.

Part 2 (one iteration, default iter4 - the converged result): a richer behavioral
profile built from final_trips, final_tours, final_persons and final_households:
purpose splits, trip rates, daily activity patterns, time-of-day, trip length and
travel time, deeper mode-share cuts, transit access/submode, auto ownership, VMT,
and a few equity cuts.

Everything is written to <base_path>/summaries as CSV files plus one combined HTML
report. Runs as a Databricks job (spark_python_task) on serverless and interactively.

Notes on the data (from the schema peek):
  * final_trips already has `distance` and `travel_time`, so no skims are needed.
  * The only nanosecond-timestamp table is final_checkpoints, which is never read,
    so Spark reads trips/tours/persons/households without special handling.

Serverless constraints respected throughout:
  * No .cache()/.persist(); DataFrames stay lazy. Every result is materialized to
    pandas (via toPandas/collect) BEFORE the temp directory is removed, so the temp
    dir can be cleaned up safely at the very end.
  * /Volumes paths are read/written directly with Python file APIs (never /dbfs).
"""

import os
import sys
import shutil
import uuid
import traceback
import zipfile
from datetime import datetime
from typing import List, Tuple, Optional

import pandas as pd
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F


DEFAULT_BASE_PATH = "/Volumes/forecasting_dev/learning/files/activitysim_test_output/outputs"
ITERATIONS = [1, 2, 3, 4]          # iterations for the cross-iteration mode-share comparison
ITERATION_DETAIL = 4               # iteration used for the detailed profile (the converged one)

# Standard ActivitySim person types (label is best-effort; a local config may differ).
PTYPE_LABELS = {
    1: "1 Full-time worker", 2: "2 Part-time worker", 3: "3 University student",
    4: "4 Non-working adult", 5: "5 Retired", 6: "6 Driving-age student",
    7: "7 Non-driving student", 8: "8 Pre-school child",
}
ACCESS_LABELS = {"WLK": "Walk access", "PNR": "Park-and-ride", "KNR": "Kiss-and-ride"}
SUBMODE_LABELS = {"BUS": "Bus", "RAL": "Rail / SkyTrain", "WCE": "West Coast Express"}
# Assumed vehicle occupancy for the VMT estimate. TNC and transit are excluded.
AUTO_OCCUPANCY = {"DRIVEALONE": 1.0, "SHARED2": 2.0, "SHARED3": 3.5}
DIST_BANDS = ["0-1", "1-2", "2-5", "5-10", "10-15", "15-25", "25-40", "40+"]
AGE_BANDS = ["0-15", "16-24", "25-44", "45-64", "65+"]


# --------------------------------------------------------------------------- #
# Output writers
# --------------------------------------------------------------------------- #

def write_csv(df: DataFrame, name: str, output_dir: str):
    """Collect a small summary DataFrame to pandas and write one clean CSV.

    Returns the pandas DataFrame so it can be reused for the HTML report.
    """
    os.makedirs(output_dir, exist_ok=True)
    pdf = df.toPandas()
    csv_path = f"{output_dir}/{name}.csv"
    pdf.to_csv(csv_path, index=False)
    print(f"  Wrote {csv_path}")
    return pdf


def write_pandas_csv(pdf: "pd.DataFrame", name: str, output_dir: str):
    """Write an already-materialized pandas DataFrame to CSV."""
    os.makedirs(output_dir, exist_ok=True)
    csv_path = f"{output_dir}/{name}.csv"
    pdf.to_csv(csv_path, index=False)
    print(f"  Wrote {csv_path}")
    return pdf


def write_html_report(named_tables: List[Tuple[str, "object"]], base_path: str, output_dir: str):
    """Write a single, styled HTML report containing all tables.

    named_tables: list of (title, pandas_DataFrame). A None DataFrame renders the
    title as a full-width section banner instead of a table.
    """
    css = (
        "body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:32px;color:#1a1a1a;}"
        "h1{font-size:22px;margin:36px 0 8px;border-bottom:3px solid #333;padding-bottom:6px;}"
        "p.meta{color:#666;font-size:13px;margin-top:0;}"
        "h2{font-size:16px;margin-top:28px;border-bottom:2px solid #eee;padding-bottom:4px;}"
        "table{border-collapse:collapse;margin:8px 0 4px;font-size:13px;}"
        "th,td{border:1px solid #ddd;padding:6px 12px;text-align:right;}"
        "th{background:#f5f5f5;}"
        "td:first-child,th:first-child{text-align:left;font-weight:500;}"
        "tr:nth-child(even){background:#fafafa;}"
    )
    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        f"<title>ActivitySim Travel Summary</title><style>{css}</style></head><body>",
        "<h1 style='border:none'>ActivitySim Travel Summary</h1>",
        f"<p class='meta'>Source: {base_path}<br>Generated: {datetime.now():%Y-%m-%d %H:%M}</p>",
    ]
    for title, pdf in named_tables:
        if pdf is None:
            parts.append(f"<h1>{title}</h1>")
            continue
        parts.append(f"<h2>{title}</h2>")
        parts.append(pdf.to_html(index=False, border=0))
    parts.append("</body></html>")

    html_path = f"{output_dir}/activitysim_summary_report.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    print(f"  Wrote {html_path}")


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #

def extract_parquet_from_zip(zip_path: str, parquet_filename: str, temp_dir: str) -> str:
    """Extract a parquet file from a zip into a temp dir in a UC volume.

    /Volumes paths are read/written directly with Python file APIs on serverless.
    Do NOT convert to /dbfs - /dbfs/Volumes is reserved and cannot access volumes.
    Matches on suffix so the in-zip `output/` prefix is handled automatically.
    """
    print(f"  Extracting {parquet_filename} from {os.path.basename(zip_path)}...")
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        matching = [f for f in zip_ref.namelist() if f.endswith(parquet_filename)]
        if not matching:
            raise FileNotFoundError(
                f"{parquet_filename} not found in {zip_path}. "
                f"Available files: {zip_ref.namelist()[:10]}..."
            )
        os.makedirs(temp_dir, exist_ok=True)
        return zip_ref.extract(matching[0], temp_dir)


# --------------------------------------------------------------------------- #
# Part 1 - cross-iteration mode share (original analysis)
# --------------------------------------------------------------------------- #

def calculate_mode_shares(df: DataFrame, mode_column: str, iteration: int, data_type: str) -> DataFrame:
    """Calculate mode shares as counts and percentages."""
    total_count = df.count()
    return (
        df.groupBy(mode_column)
        .agg(F.count("*").alias("count"))
        .withColumn("percentage", F.round((F.col("count") / total_count) * 100, 2))
        .withColumn("iteration", F.lit(iteration))
        .withColumn("type", F.lit(data_type))
        .orderBy(F.col("count").desc())
        .select("iteration", "type", F.col(mode_column).alias("mode"), "count", "percentage")
    )


def summarize_iteration(spark: SparkSession, base_path: str, iteration: int, temp_dir: str) -> Tuple[DataFrame, DataFrame]:
    """Summarize trips and tours mode share for a single iteration."""
    print(f"\n{'=' * 80}\nITERATION {iteration}\n{'=' * 80}")
    zip_path = f"{base_path}/activitysim_outputs_iter{iteration}.zip"
    iter_temp_dir = f"{temp_dir}/iter{iteration}"

    trips_df = spark.read.parquet(extract_parquet_from_zip(zip_path, "final_trips.parquet", iter_temp_dir))
    trip_mode_col = "trip_mode" if "trip_mode" in trips_df.columns else "mode"
    print(f"Total trips: {trips_df.count():,}")
    trip_shares = calculate_mode_shares(trips_df, trip_mode_col, iteration, "trips")
    trip_shares.show(50, truncate=False)

    tours_df = spark.read.parquet(extract_parquet_from_zip(zip_path, "final_tours.parquet", iter_temp_dir))
    tour_mode_col = "tour_mode" if "tour_mode" in tours_df.columns else "mode"
    print(f"Total tours: {tours_df.count():,}")
    tour_shares = calculate_mode_shares(tours_df, tour_mode_col, iteration, "tours")
    tour_shares.show(50, truncate=False)

    return trip_shares, tour_shares


def build_pivot(combined: DataFrame) -> DataFrame:
    return (
        combined.groupBy("mode")
        .pivot("iteration", ITERATIONS)
        .agg(F.first("percentage"))
        .orderBy(F.col(str(ITERATIONS[-1])).desc_nulls_last())
    )


def build_change(first_shares: DataFrame, last_shares: DataFrame) -> DataFrame:
    a = first_shares.withColumnRenamed("percentage", "iter1_pct").select("mode", "iter1_pct")
    b = last_shares.withColumnRenamed("percentage", "iter4_pct").select("mode", "iter4_pct")
    return (
        a.join(b, "mode", "outer")
        .withColumn("change", F.round(F.col("iter4_pct") - F.col("iter1_pct"), 2))
        .orderBy(F.abs(F.col("change")).desc())
    )


def cross_iteration_mode_share(spark: SparkSession, base_path: str, temp_dir: str,
                               output_dir: str, report: List[Tuple[str, "object"]]) -> None:
    """Original cross-iteration mode-share analysis; appends results to `report`."""
    report.append(("Cross-iteration mode share (iterations 1-4)", None))
    all_trip_shares: List[DataFrame] = []
    all_tour_shares: List[DataFrame] = []

    for iteration in ITERATIONS:
        try:
            trip_shares, tour_shares = summarize_iteration(spark, base_path, iteration, temp_dir)
            all_trip_shares.append(trip_shares)
            all_tour_shares.append(tour_shares)
        except Exception as e:
            print(f"\nWarning: Could not process iteration {iteration}: {e}")
            traceback.print_exc()
            continue

    if all_trip_shares:
        combined_trips = all_trip_shares[0]
        for df in all_trip_shares[1:]:
            combined_trips = combined_trips.union(df)
        report.append(("Trip mode shares by iteration (%)",
                       write_csv(build_pivot(combined_trips), "trip_mode_shares_by_iteration", output_dir)))
        report.append(("Trip mode shares - detail (counts)",
                       write_csv(combined_trips, "trip_mode_shares_detail", output_dir)))

    if all_tour_shares:
        combined_tours = all_tour_shares[0]
        for df in all_tour_shares[1:]:
            combined_tours = combined_tours.union(df)
        report.append(("Tour mode shares by iteration (%)",
                       write_csv(build_pivot(combined_tours), "tour_mode_shares_by_iteration", output_dir)))
        report.append(("Tour mode shares - detail (counts)",
                       write_csv(combined_tours, "tour_mode_shares_detail", output_dir)))

    if len(all_trip_shares) >= 2:
        report.append(("Trip mode share changes (iter 1 -> 4, pp)",
                       write_csv(build_change(all_trip_shares[0], all_trip_shares[-1]), "trip_mode_share_changes", output_dir)))
        report.append(("Tour mode share changes (iter 1 -> 4, pp)",
                       write_csv(build_change(all_tour_shares[0], all_tour_shares[-1]), "tour_mode_share_changes", output_dir)))


# --------------------------------------------------------------------------- #
# Part 2 helpers - detailed profile
# --------------------------------------------------------------------------- #

def label_col(col: str, mapping: dict, prefix: str = ""):
    """Build a Spark column that maps coded values to readable labels."""
    expr = None
    for k, v in mapping.items():
        cond = F.col(col) == k
        expr = F.when(cond, v) if expr is None else expr.when(cond, v)
    return expr.otherwise(F.concat(F.lit(prefix), F.col(col).cast("string")))


def distribution(df: DataFrame, col: str, label: str, total: int, by_value: bool = False) -> DataFrame:
    """Count + percentage of each value of `col`."""
    out = (
        df.groupBy(col)
        .agg(F.count("*").alias("count"))
        .withColumn("percentage", F.round(F.col("count") / total * 100, 2))
    )
    out = out.orderBy(F.col(col).asc()) if by_value else out.orderBy(F.col("count").desc())
    return out.withColumnRenamed(col, label)


def share_pivot(df: DataFrame, row_col: str, seg_col: str, row_label: str,
                seg_values: Optional[list] = None) -> DataFrame:
    """% of each `seg_col` group that falls in each `row_col` value (columns sum ~100)."""
    by = df.groupBy(row_col, seg_col).agg(F.count("*").alias("c"))
    tot = df.groupBy(seg_col).agg(F.count("*").alias("t"))
    pct = by.join(tot, seg_col).withColumn("pct", F.round(F.col("c") / F.col("t") * 100, 2))
    g = pct.groupBy(row_col)
    g = g.pivot(seg_col, seg_values) if seg_values else g.pivot(seg_col)
    return g.agg(F.first("pct")).na.fill(0).orderBy(row_col).withColumnRenamed(row_col, row_label)


def with_dist_band(df: DataFrame, col: str = "distance") -> DataFrame:
    band = (F.when(F.col(col) < 1, "0-1").when(F.col(col) < 2, "1-2")
            .when(F.col(col) < 5, "2-5").when(F.col(col) < 10, "5-10")
            .when(F.col(col) < 15, "10-15").when(F.col(col) < 25, "15-25")
            .when(F.col(col) < 40, "25-40").otherwise("40+"))
    idx = (F.when(F.col(col) < 1, 0).when(F.col(col) < 2, 1)
           .when(F.col(col) < 5, 2).when(F.col(col) < 10, 3)
           .when(F.col(col) < 15, 4).when(F.col(col) < 25, 5)
           .when(F.col(col) < 40, 6).otherwise(7))
    return df.withColumn("dist_band", band).withColumn("dist_band_idx", idx)


def with_age_band(df: DataFrame, col: str = "age") -> DataFrame:
    band = (F.when(F.col(col) < 16, "0-15").when(F.col(col) < 25, "16-24")
            .when(F.col(col) < 45, "25-44").when(F.col(col) < 65, "45-64").otherwise("65+"))
    return df.withColumn("age_band", band)


def _section(report, title, fn):
    """Run one block of the detailed profile, isolating failures."""
    try:
        fn()
    except Exception as e:
        print(f"\nWarning: detail section '{title}' failed: {e}")
        traceback.print_exc()


# --------------------------------------------------------------------------- #
# Part 2 - detailed profile for one iteration
# --------------------------------------------------------------------------- #

def summarize_iteration_detail(spark: SparkSession, base_path: str, iteration: int,
                               temp_dir: str, output_dir: str, report: List[Tuple[str, "object"]]) -> None:
    print(f"\n{'=' * 80}\nITERATION {iteration} - DETAILED PROFILE\n{'=' * 80}")
    report.append((f"Iteration {iteration} - detailed travel profile", None))

    zip_path = f"{base_path}/activitysim_outputs_iter{iteration}.zip"
    d = f"{temp_dir}/detail_iter{iteration}"

    trips = spark.read.parquet(extract_parquet_from_zip(zip_path, "final_trips.parquet", d))
    tours = spark.read.parquet(extract_parquet_from_zip(zip_path, "final_tours.parquet", d))
    persons = spark.read.parquet(extract_parquet_from_zip(zip_path, "final_persons.parquet", d))
    households = spark.read.parquet(extract_parquet_from_zip(zip_path, "final_households.parquet", d))

    n_trips, n_tours = trips.count(), tours.count()
    n_persons, n_hh = persons.count(), households.count()
    print(f"trips={n_trips:,}  tours={n_tours:,}  persons={n_persons:,}  households={n_hh:,}")

    trip_mode = "trip_mode" if "trip_mode" in trips.columns else "mode"

    # ---- Trip generation & rates ---------------------------------------- #
    def _rates():
        autos_per_hh = households.agg(F.avg("auto_ownership")).collect()[0][0]
        rates = pd.DataFrame({
            "metric": ["Trips", "Tours", "Persons", "Households",
                       "Trips per person", "Tours per person", "Trips per household",
                       "Tours per household", "Trips per tour", "Persons per household",
                       "Autos per household"],
            "value": [n_trips, n_tours, n_persons, n_hh,
                      round(n_trips / n_persons, 3), round(n_tours / n_persons, 3),
                      round(n_trips / n_hh, 3), round(n_tours / n_hh, 3),
                      round(n_trips / n_tours, 3), round(n_persons / n_hh, 3),
                      round(autos_per_hh, 3)],
        })
        report.append(("Trip generation & rates", write_pandas_csv(rates, "trip_rates", output_dir)))

        rate_map = [("Work", "num_work_tours"), ("Mandatory (all)", "num_mand"),
                    ("Escort", "num_escort_tours"), ("Shopping", "num_shop_tours"),
                    ("Maintenance", "num_maint_tours"), ("Eat out", "num_eatout_tours"),
                    ("Social", "num_social_tours"), ("Discretionary", "num_discr_tours"),
                    ("Non-mandatory (all)", "num_non_mand"), ("Joint", "num_joint_tours")]
        present = [(lbl, c) for lbl, c in rate_map if c in persons.columns]
        if present:
            row = persons.agg(*[F.round(F.avg(c), 3).alias(c) for _, c in present]).collect()[0]
            tpp = pd.DataFrame({"tour_purpose": [lbl for lbl, _ in present],
                                "avg_tours_per_person": [row[c] for _, c in present]})
            report.append(("Tours per person, by purpose", write_pandas_csv(tpp, "tours_per_person_by_purpose", output_dir)))
    _section(report, "rates", _rates)

    # ---- Purpose splits -------------------------------------------------- #
    def _purpose():
        report.append(("Trip purpose split", write_csv(distribution(trips, "purpose", "purpose", n_trips),
                                                        "trip_purpose_split", output_dir)))
        report.append(("Tour purpose split (tour_type)", write_csv(distribution(tours, "tour_type", "tour_type", n_tours),
                                                                    "tour_purpose_split", output_dir)))
        report.append(("Tour category split", write_csv(distribution(tours, "tour_category", "tour_category", n_tours),
                                                         "tour_category_split", output_dir)))
        if "stop_frequency" in tours.columns:
            report.append(("Tour stop frequency", write_csv(distribution(tours, "stop_frequency", "stop_frequency", n_tours),
                                                             "tour_stop_frequency", output_dir)))
    _section(report, "purpose", _purpose)

    # ---- Daily activity patterns & person types ------------------------- #
    def _activity():
        if "cdap_activity" in persons.columns:
            report.append(("Daily activity pattern (CDAP)",
                           write_csv(distribution(persons, "cdap_activity", "daily_activity_pattern", n_persons),
                                     "daily_activity_pattern", output_dir)))
        if "ptype" in persons.columns:
            p2 = persons.withColumn("person_type", label_col("ptype", PTYPE_LABELS))
            report.append(("Person type distribution",
                           write_csv(distribution(p2, "person_type", "person_type", n_persons, by_value=True),
                                     "person_type_distribution", output_dir)))
        if "work_from_home" in persons.columns:
            workers = persons.filter(F.col("is_worker") == True).count() if "is_worker" in persons.columns else n_persons
            wfh = persons.filter(F.col("work_from_home") == True).count()
            wfh_tbl = pd.DataFrame({
                "metric": ["Workers", "Work-from-home (usual)", "% of workers WFH"],
                "value": [workers, wfh, round(wfh / workers * 100, 2) if workers else None],
            })
            report.append(("Work-from-home", write_pandas_csv(wfh_tbl, "work_from_home", output_dir)))
        if "telecommute_frequency" in persons.columns:
            report.append(("Telecommute frequency",
                           write_csv(distribution(persons, "telecommute_frequency", "telecommute_frequency", n_persons),
                                     "telecommute_frequency", output_dir)))
    _section(report, "activity", _activity)

    # ---- Time of day ----------------------------------------------------- #
    def _tod():
        if "time_period" in trips.columns:
            report.append(("Trips by time-of-day period",
                           write_csv(distribution(trips, "time_period", "time_period", n_trips),
                                     "trips_by_time_period", output_dir)))
            report.append(("Mode share by time-of-day period",
                           write_csv(share_pivot(trips, trip_mode, "time_period", "mode"),
                                     "mode_share_by_time_period", output_dir)))
        if "depart" in trips.columns:
            report.append(("Trips by departure period",
                           write_csv(distribution(trips, "depart", "depart_period", n_trips, by_value=True),
                                     "trips_by_depart_period", output_dir)))
        if "start" in tours.columns:
            report.append(("Tours by start period",
                           write_csv(distribution(tours, "start", "start_period", n_tours, by_value=True),
                                     "tours_by_start_period", output_dir)))
        if "duration" in tours.columns and "tour_type" in tours.columns:
            dur = (tours.groupBy("tour_type")
                   .agg(F.count("*").alias("tours"), F.round(F.avg("duration"), 2).alias("avg_duration_periods"))
                   .orderBy(F.col("tours").desc()))
            report.append(("Average tour duration by purpose", write_csv(dur, "tour_duration_by_purpose", output_dir)))
    _section(report, "tod", _tod)

    # ---- Trip length & travel time --------------------------------------- #
    def _length():
        tb = with_dist_band(trips)
        dd = (tb.groupBy("dist_band_idx", "dist_band").agg(F.count("*").alias("count"))
              .withColumn("percentage", F.round(F.col("count") / n_trips * 100, 2))
              .orderBy("dist_band_idx")
              .select(F.col("dist_band").alias("distance_band"), "count", "percentage"))
        report.append(("Trip distance distribution", write_csv(dd, "trip_distance_distribution", output_dir)))

        adp = (trips.groupBy("purpose").agg(
            F.count("*").alias("trips"),
            F.round(F.avg("distance"), 2).alias("avg_distance"),
            F.round(F.avg("travel_time"), 2).alias("avg_travel_time")).orderBy(F.col("trips").desc()))
        report.append(("Avg distance & travel time by purpose", write_csv(adp, "avg_distance_time_by_purpose", output_dir)))

        adm = (trips.groupBy(trip_mode).agg(
            F.count("*").alias("trips"),
            F.round(F.avg("distance"), 2).alias("avg_distance"),
            F.round(F.avg("travel_time"), 2).alias("avg_travel_time"))
            .orderBy(F.col("trips").desc()).withColumnRenamed(trip_mode, "mode"))
        report.append(("Avg distance & travel time by mode", write_csv(adm, "avg_distance_time_by_mode", output_dir)))
    _section(report, "length", _length)

    # ---- Deeper mode-share cuts ------------------------------------------ #
    def _cuts():
        report.append(("Mode share by trip purpose",
                       write_csv(share_pivot(trips, trip_mode, "purpose", "mode"),
                                 "mode_share_by_purpose", output_dir)))
        tb = with_dist_band(trips)
        report.append(("Mode share by distance band",
                       write_csv(share_pivot(tb, trip_mode, "dist_band", "mode", DIST_BANDS),
                                 "mode_share_by_distance_band", output_dir)))
        if "income_segment_5" in trips.columns:
            report.append(("Mode share by income segment (1=low .. 5=high)",
                           write_csv(share_pivot(trips, trip_mode, "income_segment_5", "mode"),
                                     "mode_share_by_income", output_dir)))
    _section(report, "cuts", _cuts)

    # ---- Transit access mode & submode ----------------------------------- #
    def _transit():
        transit = (trips.filter(F.col(trip_mode).rlike("^(WLK|PNR|KNR)_"))
                   .withColumn("access_code", F.regexp_extract(trip_mode, "^([A-Z]+)_", 1))
                   .withColumn("submode_code", F.regexp_extract(trip_mode, "_(.+)$", 1))
                   .withColumn("access", label_col("access_code", ACCESS_LABELS))
                   .withColumn("submode", label_col("submode_code", SUBMODE_LABELS)))
        n_transit = transit.count()
        if n_transit == 0:
            return
        report.append((f"Transit trips by access mode (of {n_transit:,} transit trips)",
                       write_csv(distribution(transit, "access", "access_mode", n_transit), "transit_by_access_mode", output_dir)))
        report.append(("Transit trips by submode",
                       write_csv(distribution(transit, "submode", "submode", n_transit), "transit_by_submode", output_dir)))
        crosstab = (transit.groupBy("access").pivot("submode").agg(F.count("*")).na.fill(0))
        report.append(("Transit access x submode (trip counts)", write_csv(crosstab, "transit_access_submode", output_dir)))
    _section(report, "transit", _transit)

    # ---- Auto ownership -------------------------------------------------- #
    def _autos():
        report.append(("Auto ownership distribution",
                       write_csv(distribution(households, "auto_ownership", "autos", n_hh, by_value=True),
                                 "auto_ownership_distribution", output_dir)))
        if "income_segment" in households.columns:
            report.append(("Auto ownership by income segment (% within income)",
                           write_csv(share_pivot(households, "auto_ownership", "income_segment", "autos"),
                                     "auto_ownership_by_income", output_dir)))
    _section(report, "autos", _autos)

    # ---- VMT & person-miles ---------------------------------------------- #
    def _vmt():
        total_pmt = trips.agg(F.sum("distance")).collect()[0][0] or 0.0
        pm = (trips.groupBy(trip_mode).agg(
            F.round(F.sum("distance"), 1).alias("person_miles"), F.count("*").alias("trips"))
            .withColumn("pct_of_person_miles", F.round(F.col("person_miles") / total_pmt * 100, 2))
            .orderBy(F.col("person_miles").desc()).withColumnRenamed(trip_mode, "mode"))
        report.append(("Person-distance by mode", write_csv(pm, "person_miles_by_mode", output_dir)))

        occ_expr = None
        for m, occ in AUTO_OCCUPANCY.items():
            cond = F.col(trip_mode) == m
            term = F.col("distance") / occ
            occ_expr = F.when(cond, term) if occ_expr is None else occ_expr.when(cond, term)
        occ_expr = occ_expr.otherwise(F.lit(None))
        vmt = trips.select(F.sum(occ_expr).alias("v")).collect()[0]["v"] or 0.0
        auto_pmt = (trips.filter(F.col(trip_mode).isin(list(AUTO_OCCUPANCY.keys())))
                    .agg(F.sum("distance")).collect()[0][0] or 0.0)
        vmt_tbl = pd.DataFrame({
            "metric": ["Total person-distance (all modes)", "Auto person-distance",
                       "Estimated vehicle-distance (VMT)", "VMT per person",
                       "VMT per household", "Avg trip distance (all modes)"],
            "value": [round(total_pmt, 1), round(auto_pmt, 1), round(vmt, 1),
                      round(vmt / n_persons, 3), round(vmt / n_hh, 3),
                      round(total_pmt / n_trips, 3)],
        })
        report.append(("VMT & person-distance summary (occupancy 1 / 2 / 3.5; TNC & transit excluded)",
                       write_pandas_csv(vmt_tbl, "vmt_summary", output_dir)))
    _section(report, "vmt", _vmt)

    # ---- Equity cuts (joins) --------------------------------------------- #
    def _equity():
        if "auto_ownership" in households.columns:
            th = trips.select(trip_mode, "household_id").join(
                households.select("household_id", "auto_ownership"), "household_id")
            report.append(("Mode share by household auto ownership",
                           write_csv(share_pivot(th, trip_mode, "auto_ownership", "mode"),
                                     "mode_share_by_auto_ownership", output_dir)))
            zv = th.filter(F.col("auto_ownership") == 0)
            n_zv = zv.count()
            if n_zv:
                report.append((f"Mode share, zero-vehicle households ({n_zv:,} trips)",
                               write_csv(distribution(zv, trip_mode, "mode", n_zv), "mode_share_zero_vehicle_hh", output_dir)))
        if "age" in persons.columns:
            tp = with_age_band(trips.select(trip_mode, "person_id").join(
                persons.select("person_id", "age"), "person_id"))
            report.append(("Mode share by age band",
                           write_csv(share_pivot(tp, trip_mode, "age_band", "mode", AGE_BANDS),
                                     "mode_share_by_age_band", output_dir)))
    _section(report, "equity", _equity)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

def run_analysis(spark: SparkSession, base_path: str) -> None:
    temp_dir = f"{base_path}/sumit/temp_analysis_{uuid.uuid4().hex[:8]}"
    output_dir = f"{base_path}/sumit/summaries"
    report: List[Tuple[str, "object"]] = []

    try:
        os.makedirs(temp_dir, exist_ok=True)
        print(f"\nUsing temporary directory: {temp_dir}")

        cross_iteration_mode_share(spark, base_path, temp_dir, output_dir, report)

        try:
            summarize_iteration_detail(spark, base_path, ITERATION_DETAIL, temp_dir, output_dir, report)
        except Exception as e:
            print(f"\nWarning: detailed profile failed: {e}")
            traceback.print_exc()

        if report:
            print(f"\nWriting combined HTML report to: {output_dir}")
            write_html_report(report, base_path, output_dir)

    finally:
        print(f"\nCleaning up temporary directory: {temp_dir}")
        shutil.rmtree(temp_dir, ignore_errors=True)


def main() -> None:
    base_path = DEFAULT_BASE_PATH
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        base_path = sys.argv[1]

    spark = SparkSession.builder.getOrCreate()

    print(f"\n{'=' * 80}\nActivitySim Travel Summary\n{'=' * 80}")
    print(f"Base path: {base_path}")
    print(f"Cross-iteration mode share: {ITERATIONS}")
    print(f"Detailed profile: iteration {ITERATION_DETAIL}")
    print(f"{'=' * 80}")

    run_analysis(spark, base_path)

    print(f"\n{'=' * 80}\nANALYSIS COMPLETE\n{'=' * 80}")


if __name__ == "__main__":
    main()