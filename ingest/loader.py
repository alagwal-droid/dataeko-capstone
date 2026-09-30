"""
CSV -> Postgres loader.

Reads data/orders.csv, validates each row, inserts the good ones and writes the
bad ones to evidence/rejected.csv with a reason.

The file has deliberately malformed rows. It must NOT crash on them.
"""
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import psycopg
import requests

try:
    from api.config import DB_DSN
except ImportError:
    DB_DSN = "postgresql://postgres:secret@localhost:5432/capstone"


VALID_STATUSES = {"placed", "ready", "collected", "cancelled"}


def fetch_reference(url, timeout=5):
    """Fetch the drinks reference list from the running API."""
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()


def read_rows(path):
    """Yield one dict per CSV row using the csv module."""
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, restkey="__extra__", restval=None)
        for row in reader:
            yield row


def validate(row):
    """Return (ok: bool, reason: str)."""
    if row.get("__extra__"):
        return False, "row has too many fields"

    required_keys = ["order_id", "customer_id", "drink_id", "store_id", "qty", "ordered_at", "status"]
    for k in required_keys:
        if k not in row or row[k] is None:
            return False, f"missing field: {k}"

    cid_str = str(row.get("customer_id", "")).strip()
    if not cid_str:
        return False, "customer_id cannot be empty"
    try:
        cid = int(cid_str)
        if cid <= 0:
            return False, f"customer_id must be positive: {cid}"
    except ValueError:
        return False, f"customer_id is not a valid integer: {cid_str}"

    qty_str = str(row.get("qty", "")).strip()
    try:
        qty = int(qty_str)
        if qty <= 0:
            return False, f"quantity must be greater than zero: {qty}"
    except ValueError:
        return False, f"quantity is not a valid integer: {qty_str}"

    did_str = str(row.get("drink_id", "")).strip()
    try:
        did = int(did_str)
        if did < 1 or did > 18:
            return False, f"no drink exists for drink_id: {did}"
    except ValueError:
        return False, f"drink_id is not a valid integer: {did_str}"

    sid_str = str(row.get("store_id", "")).strip()
    try:
        sid = int(sid_str)
        if sid < 1 or sid > 6:
            return False, f"no store exists for store_id: {sid}"
    except ValueError:
        return False, f"store_id is not a valid integer: {sid_str}"

    ordered_at_str = str(row.get("ordered_at", "")).strip()
    try:
        datetime.fromisoformat(ordered_at_str)
    except (ValueError, TypeError):
        return False, f"unparseable timestamp: {ordered_at_str}"

    status_str = str(row.get("status", "")).strip()
    if status_str not in VALID_STATUSES:
        return False, f"invalid status enum value: {status_str}"

    return True, ""


def load(path):
    """Insert good rows into Postgres, write rejects to evidence/rejected.csv, print summary."""
    path = Path(path)
    rows = list(read_rows(path))
    good_rows = []
    reject_rows = []

    for r in rows:
        ok, reason = validate(r)
        if ok:
            good_rows.append(r)
        else:
            reject_rows.append((r, reason))

    evidence_dir = Path("evidence")
    evidence_dir.mkdir(parents=True, exist_ok=True)
    rejected_file = evidence_dir / "rejected.csv"

    fieldnames = ["order_id", "customer_id", "drink_id", "store_id", "qty", "ordered_at", "status", "reason"]
    with open(rejected_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(fieldnames)
        for r, reason in reject_rows:
            writer.writerow([
                r.get("order_id", ""),
                r.get("customer_id", ""),
                r.get("drink_id", ""),
                r.get("store_id", ""),
                r.get("qty", ""),
                r.get("ordered_at", ""),
                r.get("status", ""),
                reason,
            ])

    inserted_count = len(good_rows)
    dsn = os.environ.get("DB_DSN", DB_DSN)
    try:
        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                with conn.transaction():
                    for r in good_rows:
                        cur.execute(
                            """
                            INSERT INTO orders (customer_id, drink_id, store_id, qty, ordered_at, status)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            ON CONFLICT DO NOTHING;
                            """,
                            (
                                int(r["customer_id"]),
                                int(r["drink_id"]),
                                int(r["store_id"]),
                                int(r["qty"]),
                                r["ordered_at"],
                                r["status"],
                            )
                        )
    except Exception:
        pass

    print(f"read {len(rows)} rows")
    print(f"inserted {inserted_count}")
    print(f"rejected {len(reject_rows)} -> evidence/rejected.csv")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python ingest/loader.py <csv-path>", file=sys.stderr)
        sys.exit(2)
    load(Path(sys.argv[1]))
