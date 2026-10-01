# Recruiter Bot + SQL Detective

> An explainable, high-performance candidate-job matching service and SQL investigative solution built with **Python 3.12**, **FastAPI**, raw parameterised **SQL**, and **MySQL 8**.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Quickstart & Running Locally](#2-quickstart--running-locally)
   - [Running with Docker Compose (Recommended)](#option-a-docker-compose-one-command)
   - [Running Locally on Host](#option-b-running-locally-on-host)
3. [Verified cURL Examples](#3-verified-curl-examples)
4. [Database Design & Persisted Matches Trade-Off](#4-database-design--persisted-matches-trade-off)
5. [The Matching Algorithm (Explainable & Pure)](#5-the-matching-algorithm-explainable--pure)
6. [Part 2: The SQL Detective Challenge](#6-part-2-the-sql-detective-challenge)
7. [Testing & Quality Gates](#7-testing--quality-gates)
8. [Design Decisions & Interview Walkthrough Notes](#8-design-decisions--interview-walkthrough-notes)
9. [AI Tools Disclosure](#9-ai-tools-disclosure)

---

## 1. Architecture Overview

Recruiter Bot is structured using a strict **layered clean architecture** with clear separation of concerns:

```
FastAPI Routers (HTTP Layer)
         │  (Request validation, status codes, OpenAPI docs)
         ▼
Application Services (Business Logic)
         │  (Ingestion orchestration, transaction boundaries, recomputation)
         ▼
Pure Scoring Engine (Pure Domain Logic)
         │  (Deterministic weights, skill overlap, experience fit, zero I/O)
         ▼
Repositories (Data Access Layer)
         │  (Hand-written parameterised SQL only, 0 ORM, 0 f-strings)
         ▼
MySQL 8.0 Database
         (InnoDB, foreign keys, ON DELETE CASCADE, CHECK constraints)
```

### Key Technical Non-Negotiables
- **Zero ORM or Query Builders**: No SQLAlchemy ORM, Peewee, Tortoise, or query-generating abstractions. All SQL queries and DDL migrations are hand-written.
- **Zero String-Formatted SQL**: All queries use strict parameter binding (`%s` placeholders). Dynamic `IN (...)` queries build placeholder lists like `", ".join(["%s"] * n)` with bound parameter tuples.
- **Strict Static Typing**: 100% type-annotated codebase passing `mypy --strict app` with zero errors across 23 source files.
- **Deterministic Ranking**: Stable sorting on `score DESC, skill_score DESC, availability_score DESC, id ASC`.
- **Pure Scoring Core**: The scoring logic (`app/services/scoring.py`) is completely pure with zero I/O and zero database calls, allowing fast unit test coverage.
- **Sync Endpoints for Blocking DB Driver**: FastAPI sync route definitions (`def`, not `async def`) ensure blocking MySQL connector socket I/O is run in FastAPI's external threadpool rather than stalling the async event loop.

---

## 2. Quickstart & Running Locally

### Option A: Docker Compose (One Command)

The easiest way to run the database, run migrations, and launch the service:

```bash
# 1. Clone repository
git clone <repo-url>
cd recruiter-bot

# 2. Copy environment file
cp .env.example .env

# 3. Build and launch services
docker compose up --build -d

# 4. Seed database with candidates and jobs
docker compose exec app python -m app.seed
```

The service is now listening at `http://localhost:8000`. Interactive OpenAPI documentation is available at `http://localhost:8000/docs`.

### Option B: Running Locally on Host

If you have MySQL 8 installed locally (e.g. on `localhost:3306`):

```bash
# 1. Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -e ".[dev]"

# 3. Configure .env with your local MySQL credentials
cp .env.example .env
# Edit .env: set DB_HOST, DB_USER, DB_PASSWORD, DB_NAME (default: recruiter_bot)

# 4. Run migrations and seed data
python -m app.seed

# 5. Start the development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 3. Verified cURL Examples

All endpoints return uniform JSON. Interactive Swagger UI is at `http://localhost:8000/docs`.

### 1. Health & Database Connectivity
```bash
curl -s http://localhost:8000/health | jq .
```
```json
{
  "status": "ok",
  "database": "connected",
  "version": "0.1.0"
}
```

### 2. Ingest Seed Data (Idempotent)
```bash
curl -s -X POST http://localhost:8000/ingest | jq .
```
```json
{
  "candidates": 15,
  "jobs": 6,
  "matches": 31
}
```

### 3. Get Ranked Candidates for a Job (`GET /jobs/{id}/matches`)
```bash
curl -s "http://localhost:8000/jobs/1/matches?limit=3" | jq .
```
```json
{
  "job": {
    "id": 1,
    "title": "Backend Detective",
    "min_experience_years": 3.0
  },
  "total": 2,
  "limit": 3,
  "offset": 0,
  "matches": [
    {
      "rank": 1,
      "candidate": {
        "id": 1,
        "full_name": "Sherlock H.",
        "experience_years": 8.0,
        "availability": "immediate"
      },
      "score": 95.0,
      "breakdown": {
        "skills": 1.0,
        "experience": 1.0,
        "culture": 0.5,
        "availability": 1.0
      },
      "matched_skills": [
        "deduction",
        "forensics",
        "pattern-recognition"
      ],
      "missing_skills": [],
      "reason": "Covers 3/3 required skills (deduction, forensics, pattern-recognition); 8 yrs vs 3 min; culture: analytical; available immediately."
    }
  ]
}
```

### 4. Get Ranked Jobs for a Candidate (`GET /candidates/{id}/matches`)
```bash
curl -s "http://localhost:8000/candidates/1/matches" | jq .
```
```json
{
  "candidate": {
    "id": 1,
    "full_name": "Sherlock H.",
    "experience_years": 8.0,
    "availability": "immediate"
  },
  "total": 1,
  "limit": 10,
  "offset": 0,
  "matches": [
    {
      "rank": 1,
      "job": {
        "id": 1,
        "title": "Backend Detective",
        "min_experience_years": 3.0
      },
      "score": 95.0,
      "breakdown": {
        "skills": 1.0,
        "experience": 1.0,
        "culture": 0.5,
        "availability": 1.0
      },
      "matched_skills": [
        "deduction",
        "forensics",
        "pattern-recognition"
      ],
      "missing_skills": [],
      "reason": "Covers 3/3 required skills (deduction, forensics, pattern-recognition); 8 yrs vs 3 min; culture: analytical; available immediately."
    }
  ]
}
```

### 5. Filter Matches by Availability and Minimum Score Threshold
```bash
curl -s "http://localhost:8000/jobs/2/matches?availability=immediate&min_score=50" | jq .
```

### 6. Create Candidate (Triggers Automatic Match Scoring)
```bash
curl -s -X POST http://localhost:8000/candidates \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Linus Torvalds",
    "experience_years": 25.0,
    "availability": "immediate",
    "skills": ["systems-design", "rapid-prototyping"],
    "traits": ["direct", "innovative"],
    "quirk": "Prefers git commit messages to small talk."
  }' | jq .
```

### 7. Recompute All Matches
```bash
curl -s -X POST http://localhost:8000/matches/recompute | jq .
```

---

## 4. Database Design & Persisted Matches Trade-Off

The schema is created via hand-written DDL in [`db/migrations/001_init.sql`](file:///d:/recruiter-bot/db/migrations/001_init.sql):

- **Normalised Lookup Tables (`skills`, `traits`)**: Prevents unstructured comma-separated strings. Skills and traits are deduplicated and indexed.
- **Shared Culture Vocabulary**: Candidate traits and job culture keywords join against the same `traits` table.
- **Integrity**: Foreign keys with `ON DELETE CASCADE`, `ENUM('immediate', 'two_weeks', 'not_looking')` for availability, and `CHECK` constraints on experience and scores.
- **Zero N+1 Query Guarantee**: Listing entities with linked skills and traits is batched in 3 round trips total using SQL `IN (...)` joins.

### Persisted `matches` Table vs. On-Read Computation

| Trade-off Dimension | Persisted `matches` (Chosen Design) | Compute On-The-Fly Per Request |
|---|---|---|
| **Read Latency** | **O(log N + k)**: Instant indexed B-tree scan. | **O(candidates × skills)**: High CPU and latency on every read. |
| **Auditability & Explainability** | Stored breakdown, matched/missing skills, reason string, and `scoring_version`. | Ephemeral; disappears as soon as response finishes. |
| **A/B Testing** | Supported via `scoring_version` column. | Not possible without persisting snapshots. |
| **Write Staleness** | Must update when candidates or jobs change. | Always fresh. |

**Mitigation implemented:** Any write (`POST /candidates`, `POST /jobs`, `POST /ingest`) automatically recomputes and updates the match rows for that specific entity inside the same transaction. A full recompute endpoint (`POST /matches/recompute`) is also provided.

---

## 5. The Matching Algorithm (Explainable & Pure)

The matching algorithm is implemented in [`app/services/scoring.py`](file:///d:/recruiter-bot/app/services/scoring.py). It is **pure** (deterministic, no database or network dependencies) and evaluates four components:

$$\text{Final Score} = \text{round}\Big((0.55 \cdot S + 0.20 \cdot E + 0.10 \cdot C + 0.15 \cdot A) \times 100,\; 2\Big)$$

### 1. Skill Coverage ($S$, Weight: 0.55)
Recall-based overlap:
$$S = \frac{|\text{candidate\_skills} \cap \text{required\_skills}|}{|\text{required\_skills}|}$$
*Rationale*: A recall metric is used rather than Jaccard similarity because a candidate possessing additional skills beyond what the job requires should **never** be penalised.

### 2. Experience Fit ($E$, Weight: 0.20)
Let $\text{min} = \text{job.min\_experience\_years}$, $\text{exp} = \text{candidate.experience\_years}$, and $\text{upper} = \max(2 \cdot \text{min},\, \text{min} + 5)$:
- $\text{exp} < \text{min}$: Proportional shortfall: $\frac{\text{exp}}{\text{min}}$ (if $\text{min} = 0$, $E = 1.0$).
- $\text{min} \le \text{exp} \le \text{upper}$: Sweet spot: $E = 1.0$.
- $\text{exp} > \text{upper}$: Over-qualification decay: $1.0 - \min(0.30,\, 0.02 \times (\text{exp} - \text{upper}))$, with a safety floor at $0.70$.
*Rationale*: Being under-qualified is a technical gap; over-qualification is a minor compensation/retention risk but never disqualifying.

### 3. Culture Fit ($C$, Weight: 0.10)
Overlap between candidate traits and job culture keywords, supporting semantic synonyms/aliases (e.g., `calm-under-pressure` $\leftrightarrow$ `calm`, `tenacious` $\leftrightarrow$ `persistent`):
$$C = \frac{|\text{traits} \cap \text{culture\_keywords}|}{|\text{culture\_keywords}|}$$

### 4. Availability ($A$, Weight: 0.15)
- `immediate`: $1.0$
- `two_weeks`: $0.7$
- `not_looking`: $0.0$
*Rationale*: Passive candidates are not excluded from recruitment databases. They remain visible to recruiters but are ranked below active seekers.

### Eligibility Gate & Tie-Breakers
- **Hard Gate**: Any pair with $S = 0.0$ (zero skill overlap) is rejected immediately as noise.
- **Minimum Score Gate**: Scores below `min_score` (default: 20.0) are omitted.
- **Deterministic Tie-Break**: `score DESC, skill_score DESC, availability_score DESC, candidate_id ASC`.

---

## 6. Part 2: The SQL Detective Challenge

Located in [`sql_detective/`](file:///d:/recruiter-bot/sql_detective/):
- [`schema.sql`](file:///d:/recruiter-bot/sql_detective/schema.sql): Challenge DDL loaded as-is into `hiring_ops`.
- [`seed.sql`](file:///d:/recruiter-bot/sql_detective/seed.sql): Challenge dataset loaded as-is.
- [`sql_detective.sql`](file:///d:/recruiter-bot/sql_detective/sql_detective.sql): Submission file with all 5 queries, formatted with question numbers.

### Key Data Traps Addressed:
1. **Case-Sensitive Duplicate Identity**: Applicants 1 and 2 are the same person (`Ananya Rao`, with emails `ananya.rao@mail.com` and `Ananya.Rao@mail.com`). Normalising email via `LOWER(TRIM(email))` prevents duplicate counting.
2. **Missing `applications` Table**: In this schema, job applications are inferred from interview records (`interviews.job_posting_id`).
3. **Non-Linear Interview Funnels**: Candidates can enter at the Final stage without having a Screen or Technical stage record.
4. **Preserving Postings with Zero Candidates**: Handled using `LEFT JOIN` so postings without Final-stage candidates still output `0`.

### Executed Results on MySQL 8:

| Question | Answer Summary | Output Verification |
|---|---|---|
| **Q1: Open job postings** | Postings 1, 2, 4, 5 with recruiter names | 1 (Priya Shah), 2 (Daniel Ortiz), 4 (Priya Shah), 5 (Wei Zhang) |
| **Q2: Final stage applicants per job** | Deduplicated count per posting | 1 $\to$ 2, 2 $\to$ 2, 3 $\to$ 1, 4 $\to$ 2, 5 $\to$ 0, 6 $\to$ 0, 7 $\to$ 2 |
| **Q3: People applying to > 1 job** | Normalised email deduplication | Ananya Rao (1, 4), Ben Turner (1, 3), Elena Popescu (2, 7) |
| **Q4: Final conversion rate per recruiter** | Min. 3 Final interviews | Priya Shah (75.00%), Daniel Ortiz (50.00%) |
| **Q5 (Bonus): Top recruiter per department** | Window function `RANK()` | Data: Fatima Al-Sayed (1); Engineering: Priya Shah (3) |

---

## 7. Testing & Quality Gates

The test suite runs with `pytest` and includes pure unit tests, ingestion rollback tests, and end-to-end API integration tests:

```bash
# Run pytest test suite
pytest -v

# Run linting and format verification
ruff check .
ruff format --check .

# Run strict static type checking
mypy --strict app

# Run all quality checks together
make check
```

---

## 8. Design Decisions & Interview Walkthrough Notes

### 1. Why a Weighted Sum instead of Machine Learning?
In recruiting tech, explainability and compliance are paramount. A recruiter must be able to justify why candidate A was recommended over candidate B. With a weighted score, every fraction of a point is directly attributable to skills, experience, or availability.

### 2. Why Sync Route Handlers in FastAPI?
`mysql-connector-python` is a synchronous, blocking network driver. If a blocking I/O call is executed inside an `async def` route handler, it blocks Python's single-threaded event loop, preventing all concurrent requests from proceeding. By declaring routes as standard synchronous `def`, FastAPI automatically offloads each request to an isolated threadpool thread, preserving concurrency.

### 3. Future Scalability Improvements
- **Asynchronous Recomputation**: In a production environment with hundreds of thousands of candidates, full recomputation would be dispatched to a background worker queue (e.g. Celery / ARQ / Redis Stream) rather than executed inline.
- **Embedding / Vector Search for Skills**: Semantic skill matching using vector embeddings (e.g., matching "PostgreSQL" with "Relational Databases" or "Kubernetes" with "K8s").
- **Cursor-based Pagination**: For large datasets, migrating from `LIMIT / OFFSET` to keyset / cursor pagination (`WHERE (score, id) < (:last_score, :last_id)`).

---

## 9. AI Tools Disclosure

In accordance with the assignment guidelines:
- **AI Coding Assistant**: An AI assistant was used for scaffolding project boilerplate, generating test fixtures, verifying DDL constraints, and validating SQL window function edge cases.
- **Review & Validation**: All database queries, schema designs, scoring logic mathematics, and API endpoints were verified, executed against a live MySQL 8 engine, and thoroughly tested.
