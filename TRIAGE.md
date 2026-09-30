# Triage

Investigation and resolution log for the nine foundational defects identified in the orders pipeline.

## 1. `scripts/ingest.sh` is not executable
**Symptom:**
Executing the staging script returned a shell permission error:
```bash
$ ./scripts/ingest.sh data/orders.csv
zsh: permission denied: ./scripts/ingest.sh
```
Checking the file mode confirmed that the POSIX executable permission bit (`+x`) was missing:
```bash
$ ls -la scripts/ingest.sh
-rw-r--r--@ 1 abhisheksinghlagwal staff 730 Sep 30 13:42 scripts/ingest.sh
```

**Cause:**
The file was authored and committed with standard file permissions `644` (`-rw-r--r--`). Without the executable bit, POSIX operating systems reject attempts by `execve` to execute the file directly as a binary or shell script.

**Fix:**
Set the execute permission on the filesystem and update Git's index tree mode:
```bash
chmod +x scripts/ingest.sh
git update-index --chmod=+x scripts/ingest.sh
```

**Proof:**
Inspecting file mode and executing directly:
```bash
$ ls -la scripts/ingest.sh
-rwxr-xr-x  1 abhisheksinghlagwal  staff  684 Sep 30 14:01 scripts/ingest.sh

$ ./scripts/ingest.sh data/orders.csv
staged orders.csv — 209 data rows
```

**Why `git update-index --chmod=+x` was also needed:**
Running `chmod +x` only mutates the inode metadata on the local filesystem. Git stores file modes independently inside its tree objects as either `100644` (non-executable) or `100755` (executable). Without `git update-index --chmod=+x`, Git does not stage a mode transition. Anyone else pulling or cloning the repository (including CI runners, containers, and evaluators) would receive a `100644` file and hit `permission denied`.

---

## 2. Unquoted `$1` in `scripts/ingest.sh`
**Symptom:**
Passing a file path containing spaces caused Bash test operator syntax errors:
```bash
$ cp data/orders.csv "data/march orders.csv"
$ bash scripts/ingest.sh "data/march orders.csv"
scripts/ingest.sh: line 10: [: data/march: binary operator expected
```

**Cause:**
Line 10 evaluated `if [ ! -f $1 ]; then`. Because `$1` was unquoted, Bash performed word splitting on whitespace, expanding the condition to `[ ! -f data/march orders.csv ]`. The `[` utility received unexpected extra positional arguments, triggering a syntax error.

**Fix:**
Enclosed `$1` in double quotes: `if [ ! -f "$1" ]; then`. Furthermore, sanitized the CSV header extraction with `tr -d '\r'` (`header=$(head -1 "$1" | tr -d '\r')`) to ensure compatibility with Windows-style CRLF line endings (`data/orders-windows.csv`).

**Proof:**
```bash
$ ./scripts/ingest.sh "data/march orders.csv"
staged march orders.csv — 209 data rows

$ ./scripts/ingest.sh data/orders-windows.csv
staged orders-windows.csv — 20 data rows
```

---

## 3. Dockerfile copies source before installing dependencies
**Symptom:**
Modifying any application source code file caused the Docker build to invalidate layer cache and reinstall all Python dependencies on every rebuild, increasing build duration from ~1s to ~4s+.

**Cause:**
`COPY . .` appeared before `RUN pip install ...`. In Docker's build caching model, modifying any file copied into the layer invalidates that layer and all subsequent layers. Placing source copying ahead of dependency installation meant any application logic change invalidated the pip cache.

**Fix:**
Reordered instructions to copy only `requirements.txt`, execute `pip install`, and then copy the remaining project source files:
```dockerfile
COPY api/requirements.txt api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt
COPY . .
```

**Proof (build output, before and after):**
*Before (modifying api/app.py forces reinstallation):*
```
[4/4] RUN pip install --no-cache-dir -r api/requirements.txt:
0.842 Collecting flask==3.1.2
1.230 Collecting psycopg[binary]==3.2.13
...
3.980 Successfully installed flask-3.1.2 psycopg-3.2.13 ...
=> exporting to image                                                     0.4s
```
*After (modifying api/app.py uses cached dependency layer):*
```
=> [internal] load build context                                          0.0s
=> CACHED [2/4] COPY api/requirements.txt api/requirements.txt           0.0s
=> CACHED [3/4] RUN pip install --no-cache-dir -r api/requirements.txt    0.0s
=> [4/4] COPY . .                                                         0.1s
=> exporting to image                                                     0.1s
```

---

## 4. No `.dockerignore`
**Symptom:**
Running `docker build` uploaded unnecessary build artifacts and local state (such as `.git/`, `.venv/`, and `infra/.terraform/` which was ~778 MB), resulting in massive build contexts and disk exhaustion (`no space left on device`).

**Cause:**
Without a `.dockerignore` file, the Docker client tars the entire directory tree from the root working directory and sends it to the Docker daemon as the build context.

**Fix:**
Created a comprehensive `.dockerignore` file excluding VCS metadata, virtual environments, local caches, evidence files, and Terraform state:
```
.git
.gitignore
.terraform/
infra/.terraform/
.venv/
__pycache__/
*.pyc
*.pyo
*.pyd
.pytest_cache/
evidence/
data/staging/
```

**Proof (context size, before and after):**
*Before (`infra/.terraform` present without `.dockerignore`):*
```bash
=> [internal] load build context
=> => transferring context: 778.42MB
```
*After (`.dockerignore` present):*
```bash
=> [internal] load build context
=> => transferring context: 1.48kB
```

---

## 5. API key committed to the repository
**Symptom:**
Hardcoded plaintext secret token found committed in two files:
```bash
$ grep -rn "dataeko-capstone-2026-secret" .
./api/config.py:5:API_KEY = "dataeko-capstone-2026-secret"
./.github/workflows/ci.yml:18:          API_KEY: "dataeko-capstone-2026-secret"
```

**Cause:**
Developers hardcoded static credentials for convenience during development rather than retrieving them from runtime environment variables or secure repository secrets.

**Fix:**
1. In `api/config.py`, read the key from the environment:
   ```python
   API_KEY = os.environ.get("API_KEY", "")
   ```
2. In `.github/workflows/ci.yml`, bind `API_KEY` from GitHub Actions repository secrets:
   ```yaml
   env:
     API_KEY: ${{ secrets.API_KEY }}
   ```

**Is the key gone now that you deleted the line?**
No. Running `git log -p | grep dataeko-capstone-2026-secret` demonstrates that the key remains permanently embedded in prior Git commit blobs in the commit history. Anyone who clones the repository or fetches its refs can inspect past commits and extract the secret.

**What would you have to do in real life?**
1. **Immediate Revocation**: Assume the secret is compromised immediately; invalidate and rotate the API key in production credential stores so the leaked token can no longer authenticate.
2. **Access & Audit Logs Review**: Inspect authentication logs for any unauthorized API invocations during the exposure timeframe.
3. **History Rewriting**: Use tools like `git-filter-repo` or BFG Repo-Cleaner to completely purge the commit objects from repository history, followed by an administrative force push across all remote branches and tags.
4. **Secret Scanning & Guardrails**: Enforce automated secret scanning (e.g., GitHub Secret Scanning, Gitleaks, or pre-commit hooks) to block unencrypted credentials from reaching remotes.

---

## 6. `requests` call with no timeout
**Symptom:**
In `ingest/loader.py`, the `fetch_reference(url)` helper invoked `requests.get(url)` with no `timeout` argument specified.

**Cause:**
`requests.get` defaults to `timeout=None`. If a remote host establishes a TCP connection but hangs or stalls indefinitely (e.g., deadlocked worker, silent packet drop, proxy timeout), the client process blocks forever.

**Fix:**
Configured an explicit socket timeout:
```python
def fetch_reference(url, timeout=5):
    """Fetch the drinks reference list from the running API."""
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()
```

**Why a hang is worse than an error:**
An explicit error fails fast: it releases memory buffers, yields worker threads, closes file descriptors, and triggers automated retries, circuit breakers, or alert monitors. Conversely, a hang silently occupies thread pool workers and network sockets indefinitely. As incoming traffic builds, hanging connections cascade across upstream services, exhausting OS file descriptors and connection pools until the entire system becomes unresponsive without logging an error.

---

## 7. Missing index on `orders.customer_id`
**Symptom:**
Filtering orders by `customer_id` (`SELECT * FROM orders WHERE customer_id = 4242;`) required a full sequential table scan across 400,000 records.

**Plan before:**
```
Gather  (cost=1000.00..6657.33 rows=20 width=36) (actual time=0.335..9.280 rows=20 loops=1)
  Workers Planned: 2
  Workers Launched: 2
  ->  Parallel Seq Scan on orders  (cost=0.00..5655.33 rows=8 width=36) (actual time=0.435..6.287 rows=7 loops=3)
        Filter: (customer_id = 4242)
        Rows Removed by Filter: 133327
Planning Time: 0.275 ms
Execution Time: 9.313 ms
```

**Plan after:**
```
Bitmap Heap Scan on orders  (cost=4.58..80.34 rows=20 width=36) (actual time=0.013..0.080 rows=20 loops=1)
  Recheck Cond: (customer_id = 4242)
  Heap Blocks: exact=20
  ->  Bitmap Index Scan on idx_orders_customer_id  (cost=0.00..4.57 rows=20 width=0) (actual time=0.007..0.007 rows=20 loops=1)
        Index Cond: (customer_id = 4242)
Planning Time: 0.317 ms
Execution Time: 0.112 ms
```

**Timings, three runs each:**
- **No index (Seq Scan):** 11.990 ms / 10.310 ms / 9.313 ms (Average: 10.538 ms)
- **With index (Bitmap Index Scan):** 0.223 ms / 0.124 ms / 0.112 ms (Average: 0.153 ms) — **~69× speedup**

**Why the planner changed its mind:**
The `orders` table contains 400,000 rows across several thousand disk pages, but any given `customer_id` matches only ~20 records (high selectivity). In the unindexed scenario, PostgreSQL must read every table block sequentially. With a B-tree index on `customer_id`, the planner traverses tree levels in logarithmic time, produces a bitmap of pointer addresses, and visits only the exact 20 heap blocks containing matching tuples, dropping estimated execution cost from 6657.33 down to 80.34.

---

## 8. SSH open to `0.0.0.0/0`
**Symptom:**
The security group in `infra/main.tf` exposed port 22 directly to the public internet:
```hcl
ingress {
  from_port   = 22
  to_port     = 22
  protocol    = "tcp"
  cidr_blocks = ["0.0.0.0/0"]
}
```

**Why nothing warned you:**
`terraform validate` validates configuration grammar, provider schemas, and variable types; it does not evaluate operational security postures. Because `["0.0.0.0/0"]` is syntactically a valid list of CIDR strings, the compiler reports `Success! The configuration is valid.` Security misconfigurations must be detected using static policy analysis tools like `tfsec`, `trivy`, or AWS IAM Access Analyzer.

**Fix:**
Restricted the ingress CIDR block to the internal VPC address space (`10.0.0.0/16`):
```hcl
ingress {
  from_port   = 22
  to_port     = 22
  protocol    = "tcp"
  cidr_blocks = ["10.0.0.0/16"]
}
```

**What an attacker does with this:**
A publicly exposed SSH port is relentlessly probed by automated botnets performing credential stuffing, brute-force dictionary attacks, and targeting unpatched OpenSSH vulnerabilities. If an attacker gains shell access, they can query the instance metadata service (IMDS) to steal temporary IAM credentials, pivot through internal VPC subnets, access unencrypted database endpoints, and exfiltrate customer data.

---

## 9. `count` instead of `for_each`
**Plan with `count`, after removing `staging`:**
When `environments = ["dev", "prod"]` was planned against state created with `["dev", "staging", "prod"]`:
```
  # aws_s3_bucket.env[1] must be replaced
-/+ resource "aws_s3_bucket" "env" {
      ~ bucket = "alagwal-droid-capstone-staging" -> "alagwal-droid-capstone-prod" # forces replacement
    }

  # aws_s3_bucket.env[2] will be destroyed
  # (because index [2] is out of range for count)
  - resource "aws_s3_bucket" "env" {
      - bucket = "alagwal-droid-capstone-prod" -> null
    }

Plan: 1 to add, 0 to change, 2 to destroy.
```

**Plan with `for_each`, same edit:**
After converting to `for_each = toset(var.environments)`:
```
  # aws_s3_bucket.env["staging"] will be destroyed
  - resource "aws_s3_bucket" "env" {
      - bucket = "alagwal-droid-capstone-staging" -> null
    }

Plan: 0 to add, 0 to change, 1 to destroy.
```

**Why this is the most dangerous defect in the list:**
`count` identifies resource instances by their numeric list index (`[0]`, `[1]`, `[2]`). If an item in the middle of the list is deleted or shifted, every subsequent resource changes index. Terraform interprets index shifts as destroying existing production infrastructure and recreating it from scratch. In real-world environments, this results in catastrophic data loss—dropping production object storage buckets, deleting database clusters, or cycling load balancers simply because a staging resource was removed.
