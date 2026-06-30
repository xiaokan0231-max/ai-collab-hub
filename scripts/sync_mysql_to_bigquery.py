#!/usr/bin/env python3
import datetime as dt
import decimal
import json
import os
import re
import tempfile
from pathlib import Path

import pymysql
from google.cloud import bigquery


MYSQL_DB = os.environ.get("MYSQL_DB", "sns_trend_lab")
MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
MYSQL_USER = os.environ.get("MYSQL_USER", "root")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))

BQ_PROJECT = os.environ.get("BQ_PROJECT", "project-22ce0882-0fa5-4c43-9ee")
BQ_DATASET = os.environ.get("BQ_DATASET", MYSQL_DB)
BQ_LOCATION = os.environ.get("BQ_LOCATION", "asia-northeast1")
RESUME = os.environ.get("RESUME", "1") != "0"
ALWAYS_REFRESH_TABLES = {
    "analysis_runs",
    "collection_batches",
    "collection_runs",
    "collection_quota_usage",
    "keyword_candidates",
    "operation_requests",
    "skill_analysis_runs",
}


def mysql_conn(cursorclass=pymysql.cursors.DictCursor):
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DB,
        charset="utf8mb4",
        cursorclass=cursorclass,
    )


def bq_type(column):
    data_type = column["DATA_TYPE"].lower()
    column_type = column["COLUMN_TYPE"].lower()
    if data_type == "tinyint" and column_type.startswith("tinyint(1)"):
        return "BOOL"
    if data_type in {"tinyint", "smallint", "mediumint", "int", "bigint"}:
        return "INT64"
    if data_type in {"float", "double"}:
        return "FLOAT64"
    if data_type in {"decimal", "numeric"}:
        precision = column["NUMERIC_PRECISION"] or 38
        scale = column["NUMERIC_SCALE"] or 0
        return "BIGNUMERIC" if precision > 38 or scale > 9 else "NUMERIC"
    if data_type == "date":
        return "DATE"
    if data_type in {"datetime", "timestamp"}:
        return "DATETIME"
    if data_type == "time":
        return "TIME"
    if data_type == "json":
        return "JSON"
    if "blob" in data_type or data_type in {"binary", "varbinary"}:
        return "BYTES"
    return "STRING"


def normalize_value(value, field_type, is_bool=False):
    if value is None:
        return None
    if is_bool:
        return bool(value)
    if isinstance(value, dt.datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, dt.time):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    if field_type == "JSON":
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value
    return value


def get_tables_and_columns():
    with mysql_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT TABLE_NAME
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA=%s AND TABLE_TYPE='BASE TABLE'
                ORDER BY TABLE_NAME
                """,
                (MYSQL_DB,),
            )
            tables = [row["TABLE_NAME"] for row in cur.fetchall()]
            cur.execute(
                """
                SELECT TABLE_NAME, COLUMN_NAME, ORDINAL_POSITION, DATA_TYPE, COLUMN_TYPE,
                       NUMERIC_PRECISION, NUMERIC_SCALE
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=%s
                ORDER BY TABLE_NAME, ORDINAL_POSITION
                """,
                (MYSQL_DB,),
            )
            columns = {}
            for row in cur.fetchall():
                columns.setdefault(row["TABLE_NAME"], []).append(row)
            return tables, columns


def export_table_to_ndjson(table, columns, output_path):
    field_meta = []
    for col in columns:
        field_type = bq_type(col)
        field_meta.append(
            (
                col["COLUMN_NAME"],
                field_type,
                field_type == "BOOL",
            )
        )

    count = 0
    with mysql_conn(cursorclass=pymysql.cursors.SSDictCursor) as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM `{table}`")
            with output_path.open("w", encoding="utf-8") as fh:
                for row in cur:
                    normalized = {
                        name: normalize_value(row.get(name), field_type, is_bool)
                        for name, field_type, is_bool in field_meta
                    }
                    fh.write(json.dumps(normalized, ensure_ascii=False, separators=(",", ":")))
                    fh.write("\n")
                    count += 1
    return count


def make_schema(columns):
    return [
        bigquery.SchemaField(col["COLUMN_NAME"], bq_type(col), mode="NULLABLE")
        for col in columns
    ]


def create_views(client, dataset_ref):
    dataset = f"`{dataset_ref.project}.{dataset_ref.dataset_id}`"
    views = {
        "v_latest_post_metrics": f"""
            CREATE OR REPLACE VIEW {dataset}.v_latest_post_metrics AS
            WITH ranked_snapshots AS (
              SELECT s.*, ROW_NUMBER() OVER (
                PARTITION BY post_id ORDER BY observed_at DESC, id DESC
              ) AS row_num
              FROM {dataset}.post_metric_snapshots s
            )
            SELECT
              p.post_id, p.title, p.channel_id, c.title AS channel_title,
              p.published_at, p.url, p.thumbnail_url, p.category_id, p.is_available,
              s.observed_at, s.views, s.likes, s.comments, s.shares, s.saves, s.clicks
            FROM {dataset}.posts p
            JOIN {dataset}.channels c ON c.channel_id = p.channel_id
            JOIN ranked_snapshots s ON s.post_id = p.post_id AND s.row_num = 1
        """,
        "v_latest_query_metrics": f"""
            CREATE OR REPLACE VIEW {dataset}.v_latest_query_metrics AS
            WITH ranked_observations AS (
              SELECT o.*, ROW_NUMBER() OVER (
                PARTITION BY query_id ORDER BY observed_at DESC, id DESC
              ) AS row_num
              FROM {dataset}.query_observations o
            )
            SELECT
              q.id AS query_id, q.name, q.query_text, q.topic, q.enabled, q.archived_at,
              o.observed_at, o.returned_sample_count, o.estimated_total_results,
              o.total_results_is_approximate
            FROM {dataset}.tracked_queries q
            JOIN ranked_observations o ON o.query_id = q.id AND o.row_num = 1
        """,
        "v_post_growth_metrics": f"""
            CREATE OR REPLACE VIEW {dataset}.v_post_growth_metrics AS
            WITH earliest AS (
              SELECT s.*, ROW_NUMBER() OVER (
                PARTITION BY post_id ORDER BY observed_at ASC, id ASC
              ) AS row_num
              FROM {dataset}.post_metric_snapshots s
            ),
            latest AS (
              SELECT s.*, ROW_NUMBER() OVER (
                PARTITION BY post_id ORDER BY observed_at DESC, id DESC
              ) AS row_num
              FROM {dataset}.post_metric_snapshots s
            )
            SELECT
              p.post_id, p.title, p.channel_id, c.title AS channel_title,
              p.thumbnail_url, p.url, p.published_at,
              e.observed_at AS earliest_observed_at,
              l.observed_at AS latest_observed_at,
              e.views AS earliest_views,
              l.views AS latest_views,
              CAST(l.views AS INT64) - CAST(e.views AS INT64) AS views_growth_abs,
              CASE WHEN e.views > 0 THEN
                SAFE_DIVIDE(CAST(l.views AS NUMERIC) - CAST(e.views AS NUMERIC), CAST(e.views AS NUMERIC)) * 100
              END AS views_growth_pct,
              CASE WHEN DATETIME_DIFF(l.observed_at, e.observed_at, SECOND) > 0 THEN
                SAFE_DIVIDE(
                  CAST(l.views AS NUMERIC) - CAST(e.views AS NUMERIC),
                  CAST(DATETIME_DIFF(l.observed_at, e.observed_at, SECOND) AS NUMERIC) / 86400
                )
              END AS views_growth_per_day
            FROM {dataset}.posts p
            JOIN {dataset}.channels c ON c.channel_id = p.channel_id
            JOIN earliest e ON e.post_id = p.post_id AND e.row_num = 1
            JOIN latest l ON l.post_id = p.post_id AND l.row_num = 1
        """,
        "v_latest_popular_videos": f"""
            CREATE OR REPLACE VIEW {dataset}.v_latest_popular_videos AS
            SELECT
              o.region_code, o.category_id, o.rank_position, o.observed_at,
              p.post_id, p.title, p.channel_id, c.title AS channel_title,
              p.thumbnail_url, p.url, s.views, s.likes, s.comments
            FROM {dataset}.popular_video_observations o
            JOIN {dataset}.posts p ON p.post_id = o.post_id
            JOIN {dataset}.channels c ON c.channel_id = p.channel_id
            LEFT JOIN {dataset}.v_latest_post_metrics s ON s.post_id = p.post_id
            WHERE o.batch_id = (
              SELECT MAX(latest_o.batch_id)
              FROM {dataset}.popular_video_observations latest_o
              WHERE latest_o.region_code = o.region_code
                AND latest_o.category_id IS NOT DISTINCT FROM o.category_id
            )
        """,
    }
    for name, sql in views.items():
        job = client.query(sql)
        job.result()
        print(f"VIEW {name} created")


def verify_counts(client, dataset_ref, mysql_counts):
    print("\nVERIFY_ROW_COUNTS")
    mismatches = []
    for table, mysql_count in mysql_counts.items():
        query = f"SELECT COUNT(*) AS c FROM `{dataset_ref.project}.{dataset_ref.dataset_id}.{table}`"
        bq_count = list(client.query(query).result())[0]["c"]
        status = "OK" if int(bq_count) == int(mysql_count) else "MISMATCH"
        print(f"{table}\tmysql={mysql_count}\tbigquery={bq_count}\t{status}")
        if status != "OK":
            mismatches.append(table)
    return mismatches


def main():
    client = bigquery.Client(project=BQ_PROJECT)
    dataset_ref = bigquery.DatasetReference(BQ_PROJECT, BQ_DATASET)
    dataset = bigquery.Dataset(dataset_ref)
    dataset.location = BQ_LOCATION
    client.create_dataset(dataset, exists_ok=True)
    print(f"DATASET {BQ_PROJECT}.{BQ_DATASET} ready in {BQ_LOCATION}", flush=True)

    tables, columns_by_table = get_tables_and_columns()
    mysql_counts = {}

    with tempfile.TemporaryDirectory(prefix="sns_trend_lab_bq_") as tmp:
        tmpdir = Path(tmp)
        for index, table in enumerate(tables, start=1):
            if RESUME and table not in ALWAYS_REFRESH_TABLES:
                try:
                    existing = client.get_table(f"{BQ_PROJECT}.{BQ_DATASET}.{table}")
                    with mysql_conn() as conn:
                        with conn.cursor() as cur:
                            cur.execute(f"SELECT COUNT(*) AS c FROM `{table}`")
                            mysql_count = int(cur.fetchone()["c"])
                    if int(existing.num_rows) == mysql_count:
                        mysql_counts[table] = mysql_count
                        print(
                            f"\n[{index}/{len(tables)}] SKIP {table}: rows already match ({mysql_count})",
                            flush=True,
                        )
                        continue
                except Exception:
                    pass

            print(f"\n[{index}/{len(tables)}] EXPORT {table}", flush=True)
            output_path = tmpdir / f"{table}.ndjson"
            row_count = export_table_to_ndjson(table, columns_by_table[table], output_path)
            mysql_counts[table] = row_count
            size_mb = output_path.stat().st_size / 1024 / 1024
            print(f"LOAD {table}: rows={row_count}, file={size_mb:.2f}MB", flush=True)

            job_config = bigquery.LoadJobConfig(
                source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
                schema=make_schema(columns_by_table[table]),
                write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            )
            table_id = f"{BQ_PROJECT}.{BQ_DATASET}.{table}"
            with output_path.open("rb") as fh:
                load_job = client.load_table_from_file(fh, table_id, job_config=job_config)
            load_job.result()
            loaded_table = client.get_table(table_id)
            print(f"DONE {table}: bigquery_rows={loaded_table.num_rows}", flush=True)

    print("\nCREATE_VIEWS", flush=True)
    create_views(client, dataset_ref)
    mismatches = verify_counts(client, dataset_ref, mysql_counts)
    if mismatches:
        raise SystemExit(f"Row count mismatches: {', '.join(mismatches)}")
    print("\nSYNC_COMPLETE")


if __name__ == "__main__":
    main()
