"""Export page content to Parquet format for Cloudera/Hive."""
import sqlite3
from pathlib import Path
import pandas as pd


def export_to_parquet(db_path: Path, output_path: Path) -> int:
    """Export page_content joined with pages to Parquet. Returns row count."""
    conn = sqlite3.connect(db_path)

    query = """
        SELECT
            p.url,
            p.final_url,
            p.status_code,
            p.content_type,
            p.fetched_at,
            pc.title,
            pc.text_content,
            pc.page_section,
            pc.language,
            pc.extracted_at,
            pc.extractor_version
        FROM page_content pc
        JOIN pages p ON p.id = pc.page_id
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    df.to_parquet(output_path, index=False)
    return len(df)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Export to Parquet")
    parser.add_argument("db_path", type=Path, help="Path to SQLite database")
    parser.add_argument("output_path", type=Path, help="Output Parquet file")
    args = parser.parse_args()

    count = export_to_parquet(args.db_path, args.output_path)
    print(f"Exported {count} rows to {args.output_path}")
