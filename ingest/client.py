"""
Orders API Client with pagination and rate limit retry backoff.
Usage: python ingest/client.py
"""
import os
import sys
import time
import requests

API_URL = os.environ.get("API_URL", "http://localhost:8000")
API_KEY = os.environ.get("API_KEY", "test-secret-key")


def fetch_all_orders(base_url=API_URL, api_key=API_KEY, timeout=5):
    """Page through all orders, backing off on HTTP 429."""
    headers = {"Authorization": f"Bearer {api_key}"}
    page = 1
    per_page = 100
    all_orders = []
    total_expected = None

    while True:
        url = f"{base_url}/orders?page={page}&per_page={per_page}"
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
        except requests.RequestException as e:
            print(f"Request error: {e}", file=sys.stderr)
            break

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "1"))
            print(f"HTTP 429 received. Backing off for {retry_after}s...")
            time.sleep(retry_after)
            continue

        resp.raise_for_status()
        data = resp.json()
        orders = data.get("results", [])
        total_expected = data.get("total", 0)
        all_orders.extend(orders)

        count = data.get("count", len(orders))
        print(f"Page {page}: fetched {count} orders (accumulated {len(all_orders)} / {total_expected})")

        if len(all_orders) >= total_expected or count == 0:
            break

        page += 1

    print(f"Finished collecting orders: {len(all_orders)} total orders collected")
    return all_orders


if __name__ == "__main__":
    fetch_all_orders()
