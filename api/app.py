"""
Orders API — DATAEKO capstone.

Endpoints you must finish are marked TODO. Everything else works.
Run it:  flask --app api/app.py run --port 8000
"""
from collections import defaultdict
import os
import time
import psycopg
from flask import Flask, jsonify, request
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

from api.config import API_KEY, DB_DSN, PAGE_SIZE_DEFAULT, PAGE_SIZE_MAX

app = Flask(__name__)

REQUESTS = Counter(
    "capstone_requests_total",
    "Total HTTP requests",
    ["endpoint", "method", "status"],
)
LATENCY = Histogram(
    "capstone_request_seconds",
    "Request latency in seconds",
    ["endpoint"],
)

IN_FLIGHT = Gauge(
    "capstone_orders_in_flight",
    "Number of orders requests currently in flight",
)

RATE_LIMIT_REQUESTS = 10
RATE_LIMIT_WINDOW = 10.0
request_history = defaultdict(list)


def db():
    return psycopg.connect(os.environ.get("DB_DSN", DB_DSN))


def authorised(req):
    """401 = we do not know who you are. 403 = we know, and no."""
    header = req.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return 401, "missing or malformed Authorization header"
    token = header.split(" ", 1)[1]
    expected_key = os.environ.get("API_KEY", API_KEY)
    if token != expected_key or not expected_key:
        return 403, "that key is not allowed here"
    return 200, None


def check_rate_limit(token):
    now = time.time()
    timestamps = request_history[token]
    timestamps = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW]
    request_history[token] = timestamps
    if len(timestamps) >= RATE_LIMIT_REQUESTS:
        return False, int(RATE_LIMIT_WINDOW - (now - timestamps[0])) + 1
    request_history[token].append(now)
    return True, 0


@app.get("/health")
def health():
    REQUESTS.labels("/health", "GET", 200).inc()
    return jsonify(status="ok")


@app.get("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


@app.get("/orders")
def orders():
    start = time.time()
    IN_FLIGHT.inc()
    try:
        code, msg = authorised(request)
        if code != 200:
            REQUESTS.labels("/orders", "GET", code).inc()
            return jsonify(error=msg), code

        token = request.headers.get("Authorization", "").split(" ", 1)[1]
        allowed, retry_after = check_rate_limit(token)
        if not allowed:
            REQUESTS.labels("/orders", "GET", 429).inc()
            return jsonify(error="rate limit exceeded"), 429, {"Retry-After": str(max(1, retry_after))}

        try:
            page = int(request.args.get("page", 1))
            if page < 1:
                page = 1
        except ValueError:
            page = 1

        try:
            per_page = int(request.args.get("per_page", PAGE_SIZE_DEFAULT))
            if per_page < 1:
                per_page = PAGE_SIZE_DEFAULT
            elif per_page > PAGE_SIZE_MAX:
                per_page = PAGE_SIZE_MAX
        except ValueError:
            per_page = PAGE_SIZE_DEFAULT

        offset = (page - 1) * per_page

        try:
            with db() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT count(*) FROM orders;")
                    total = cur.fetchone()[0]

                    cur.execute(
                        """
                        SELECT id, customer_id, drink_id, store_id, qty, ordered_at, status
                        FROM orders
                        ORDER BY id
                        LIMIT %s OFFSET %s;
                        """,
                        (per_page, offset),
                    )
                    rows = cur.fetchall()
                    results = [
                        {
                            "id": r[0],
                            "customer_id": r[1],
                            "drink_id": r[2],
                            "store_id": r[3],
                            "qty": r[4],
                            "ordered_at": r[5].isoformat() if hasattr(r[5], "isoformat") else str(r[5]),
                            "status": r[6],
                        }
                        for r in rows
                    ]
        except Exception as e:
            REQUESTS.labels("/orders", "GET", 500).inc()
            return jsonify(error=str(e)), 500

        REQUESTS.labels("/orders", "GET", 200).inc()
        return jsonify(
            count=len(results),
            total=total,
            page=page,
            per_page=per_page,
            results=results,
        )
    finally:
        LATENCY.labels("/orders").observe(time.time() - start)
        IN_FLIGHT.dec()


@app.get("/stats")
def stats():
    REQUESTS.labels("/stats", "GET", 200).inc()
    try:
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT s.city, SUM(o.qty * d.price_inr) AS revenue
                    FROM orders o
                    JOIN stores s ON o.store_id = s.id
                    JOIN drinks d ON o.drink_id = d.id
                    WHERE o.status = 'collected'
                    GROUP BY s.city
                    ORDER BY revenue DESC;
                    """
                )
                revenue_by_city = [{"city": row[0], "revenue": int(row[1])} for row in cur.fetchall()]

                cur.execute(
                    """
                    SELECT d.name
                    FROM drinks d
                    LEFT JOIN orders o ON d.id = o.drink_id
                    WHERE o.id IS NULL
                    ORDER BY d.name;
                    """
                )
                never_ordered = [row[0] for row in cur.fetchall()]

                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM orders o
                    LEFT JOIN deliveries d ON o.id = d.order_id
                    WHERE d.id IS NULL;
                    """
                )
                undelivered_count = cur.fetchone()[0]

                cur.execute(
                    """
                    SELECT c.id, c.name, COUNT(o.id) AS order_count, SUM(o.qty * d.price_inr) AS total_spend
                    FROM customers c
                    JOIN orders o ON c.id = o.customer_id
                    JOIN drinks d ON o.drink_id = d.id
                    GROUP BY c.id, c.name
                    HAVING COUNT(o.id) > 25
                    ORDER BY order_count DESC, total_spend DESC;
                    """
                )
                loyal_customers = [
                    {
                        "customer_id": row[0],
                        "name": row[1],
                        "order_count": row[2],
                        "total_spend": int(row[3]),
                    }
                    for row in cur.fetchall()
                ]

                return jsonify(
                    revenue_by_city=revenue_by_city,
                    never_ordered_drinks=never_ordered,
                    undelivered_orders_count=undelivered_count,
                    loyal_customers_count=len(loyal_customers),
                )
    except Exception as e:
        return jsonify(error=str(e)), 500


if __name__ == "__main__":
    app.run(port=8000)
