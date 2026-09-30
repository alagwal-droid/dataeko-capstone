# DATAEKO Capstone — Ship the Coffee Company

[![ci](https://github.com/alagwal-droid/dataeko-capstone/actions/workflows/ci.yml/badge.svg)](https://github.com/alagwal-droid/dataeko-capstone/actions/workflows/ci.yml)
[![pages](https://github.com/alagwal-droid/dataeko-capstone/actions/workflows/pages.yml/badge.svg)](https://alagwal-droid.github.io/dataeko-capstone/)

Final assignment for the Studio Typo × DATAEKO five-week internship.

- **Author:** Abhishek Singh Lagwal ([alagwal-droid](https://github.com/alagwal-droid))
- **Live Status Page:** [https://alagwal-droid.github.io/dataeko-capstone/](https://alagwal-droid.github.io/dataeko-capstone/)
- **GHCR Package:** [ghcr.io/alagwal-droid/dataeko-capstone:latest](https://github.com/alagwal-droid/dataeko-capstone/pkgs/container/dataeko-capstone)
- **Score:** 28/28 checks passed (100%)

```
scripts/ingest.sh      staging script          (Week 1)
ingest/loader.py       CSV -> Postgres         (Week 2)
api/app.py             the API + /metrics      (Weeks 2, 4)
sql/                   schema, seed, queries   (Week 4)
observability/         Prometheus + Grafana    (Week 4)
Dockerfile             the image               (Week 3)
.github/workflows/     CI and Pages            (Week 3)
infra/                 Terraform -> LocalStack (Week 5)
evidence/              submission receipts & benchmarks
```

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r api/requirements.txt -r ingest/requirements.txt pytest

docker start pg
docker exec pg psql -U postgres -c "CREATE DATABASE capstone;"
docker exec -i pg psql -U postgres -d capstone < sql/schema.sql
docker exec -i pg psql -U postgres -d capstone < sql/seed.sql

./scripts/verify.sh
```

Everything runs locally. No AWS account, no credit card, no spend.
