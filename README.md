# Recruiter Bot

A small backend service that loads candidate profiles and job openings, scores every candidate-job pair, and returns ranked matches with a short, human-readable reason.

Built for the RecruiterFlow Backend Developer Assignment ("Build-a-Recruiter-Bot").

- **Part 1:** the Recruiter Bot API (Python 3.11+, FastAPI, MySQL 8, hand-written SQL, no ORM)
- **Part 2:** the SQL Detective queries, in [`sql_detective.sql`](sql_detective.sql)

---

## Contents

1. [What it does](#1-what-it-does)
2. [Install and run locally](#2-install-and-run-locally)
3. [API examples (curl)](#3-api-examples-curl)
4. [How the matching works](#4-how-the-matching-works)
5. [Design decisions and trade-offs](#5-design-decisions-and-trade-offs)
6. [Project layout and database schema](#6-project-layout-and-database-schema)
7. [Tests](#7-tests)
8. [Part 2: SQL Detective](#8-part-2-sql-detective)
9. [Use of AI tools](#9-use-of-ai-tools)

---

## 1. What it does

1. **Ingest** the 15 candidates and 6 jobs from the assignment (`python -m app.seed` or `POST /ingest`).
2. **Score** every candidate-job pair from 0 to 100.
3. **Store** the scores in a `matches` table.
4. **Serve** ranked results in both directions:
   - `GET /jobs/{id}/matches` gives the best candidates for a job.
   - `GET /candidates/{id}/matches` gives the best jobs for a candidate.

Each result includes the score, a per-dimension breakdown, matched and missing skills, and a one-line reason.

*Note:* the assignment's candidate table has 15 rows (Dwight S. is the 15th), so the seed contains 15 candidates.

---

## 2. Install and run locally

### Prerequisites

- Python 3.11 or newer
- MySQL 8.0 or newer, running locally (or via Docker)

---

### Option A: Local Host (Python + MySQL)

#### 1. Clone repository
```bash
git clone https://github.com/jeevanL16/recruiter-bot.git
cd recruiter-bot
```

#### 2. Create and activate virtual environment
```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate
```

#### 3. Install dependencies
```bash
pip install -e ".[dev]"
```

#### 4. Configure environment
```bash
cp .env.example .env        # Windows: copy .env.example .env
# Edit .env with your MySQL user and password
```

Create the database in MySQL:
```sql
CREATE DATABASE IF NOT EXISTS recruiter_bot;
```

#### 5. Run migrations, seed data, and compute matches
```bash
python -m app.seed
```
This runs the hand-written DDL in `db/migrations/001_init.sql`, loads `data/seed.json`, and computes matches. It is safe to run more than once.

#### 6. Start the API
```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
Open the interactive docs at <http://127.0.0.1:8000/docs>. Every endpoint can be tried there with the "Try it out" button.

---

### Option B: Docker Compose (One Command)

If you have Docker Desktop installed:

```bash
docker compose up --build -d
docker compose exec app python -m app.seed
```
The API is live at `http://localhost:8000` with docs at `http://localhost:8000/docs`. To run tests in Docker: `docker compose exec app pytest -v`. To stop: `docker compose down`.

---

### Environment variables

| Variable | Meaning | Example |
| :-- | :-- | :-- |
| `DB_HOST` | MySQL host | `localhost` |
| `DB_PORT` | MySQL port | `3306` |
| `DB_USER` | MySQL user | `your_user` |
| `DB_PASSWORD` | MySQL password | `your_password_here` |
| `DB_NAME` | Database name | `recruiter_bot` |
| `DB_POOL_SIZE` | Connection pool size | `5` |
| `MIN_SCORE_DEFAULT` | Default minimum score filter | `20.0` |
| `LOG_LEVEL` | Log level | `INFO` |

`.env` is git-ignored. Only `.env.example` (with placeholder values) is committed.

---

## 3. API examples (curl)

On Windows PowerShell use `curl.exe` instead of `curl`, and keep quotes around URLs that contain `?` or `&`.

| Method | Endpoint | Purpose |
| :-- | :-- | :-- |
| `GET` | `/health` | App and database health check |
| `POST` | `/ingest` | Load candidates and jobs (default: `data/seed.json`) and compute matches |
| `POST` | `/matches/recompute` | Recompute all matches |
| `GET` | `/jobs`, `/jobs/{id}` | List jobs, get one job |
| `POST` | `/jobs` | Create a job and compute its matches |
| `GET` | `/candidates`, `/candidates/{id}` | List candidates, get one candidate |
| `POST` | `/candidates` | Create a candidate and compute their matches |
| `GET` | `/jobs/{id}/matches` | **Ranked candidates for a job** |
| `GET` | `/candidates/{id}/matches` | **Ranked jobs for a candidate** |

Query parameters on both match endpoints: `limit` (1-100, default 10), `offset` (default 0), `min_score` (0-100).

### Load the data
```bash
curl -X POST http://127.0.0.1:8000/ingest
```

### Ranked candidates for job 1 (Backend Detective)
```bash
curl "http://127.0.0.1:8000/jobs/1/matches?limit=5"
```

Example response:
```json
{
  "job": { "id": 1, "title": "Backend Detective", "min_experience_years": 3.0 },
  "total": 2,
  "limit": 5,
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
      "breakdown": { "skills": 1.0, "experience": 1.0, "culture": 0.5, "availability": 1.0 },
      "matched_skills": ["deduction", "forensics", "pattern-recognition"],
      "missing_skills": [],
      "reason": "Matches 3/3 required skills; 8y vs 3y minimum; available immediately; culture 1/2."
    },
    {
      "rank": 2,
      "candidate": {
        "id": 9,
        "full_name": "Sheldon C.",
        "experience_years": 9.0,
        "availability": "immediate"
      },
      "score": 53.33,
      "breakdown": { "skills": 0.333, "experience": 1.0, "culture": 0.0, "availability": 1.0 },
      "matched_skills": ["pattern-recognition"],
      "missing_skills": ["deduction", "forensics"],
      "reason": "Matches 1/3 required skills; missing deduction, forensics; 9y vs 3y minimum; available immediately; culture 0/2."
    }
  ]
}
```

Only two candidates appear because only Sherlock and Sheldon share at least one required skill with this job.

### Ranked jobs for candidate 1 (Sherlock)
```bash
curl "http://127.0.0.1:8000/candidates/1/matches"
```

### Unknown id returns 404
```bash
curl -i "http://127.0.0.1:8000/jobs/999/matches"
```

### Create a candidate (matches are computed in the same request)
```bash
curl -X POST http://127.0.0.1:8000/candidates \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Ada Lovelace",
    "experience_years": 10,
    "availability": "immediate",
    "skills": ["systems-design", "rapid-prototyping", "mathematics"],
    "traits": ["analytical", "innovative"],
    "quirk": "Wrote the first algorithm in history."
  }'
```
`availability` must be one of `immediate`, `two_weeks`, `not_looking`.

### Create a job
```bash
curl -X POST http://127.0.0.1:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Senior Systems Architect",
    "min_experience_years": 8,
    "required_skills": ["systems-design", "rapid-prototyping"],
    "culture_keywords": ["innovative", "autonomous"],
    "tagline": "Design systems that withstand high concurrency."
  }'
```

*Note on Windows PowerShell:* inline JSON with quotes can be escaped, or saved to a file (`candidate.json`) and sent with `--data "@candidate.json"`.

---

## 4. How the matching works

Each candidate-job pair gets four sub-scores, each between 0 and 1:

```
score = 100 * (0.55 * skills + 0.20 * experience + 0.10 * culture + 0.15 * availability)
```

| Dimension | Weight | How it is calculated |
| :-- | :-: | :-- |
| **Skills** | 55% | required skills the candidate has, divided by required skills. Extra skills are not penalized. |
| **Experience** | 20% | `min(1, candidate_years / job_min_years)`. 1.0 if the job has no minimum. |
| **Culture** | 10% | job culture keywords found among the candidate's traits, divided by keywords. 1.0 if the job lists none. |
| **Availability** | 15% | `immediate` = 1.0, `two_weeks` = 0.8, `not_looking` = 0.0 |

**Hard gate:** if a candidate shares **zero** required skills with a job, no match is created for that pair.

**Tie-breaking** (so ordering and pagination are stable): `score DESC`, then `skills DESC`, then `availability DESC`, then `id ASC`.

### Worked example: Sherlock H. for Backend Detective

| Check | Result | Weight | Points |
| :-- | :-- | :-: | :-: |
| Skills: has deduction, pattern-recognition, forensics | 3/3 = 1.0 | 55 | 55 |
| Experience: 8 years vs 3 minimum | 1.0 | 20 | 20 |
| Culture: analytical matches, autonomous does not | 1/2 = 0.5 | 10 | 5 |
| Availability: immediate | 1.0 | 15 | 15 |
| **Total** | | | **95** |

### Match counts with the seed data

With the hard gate, the seed produces 31 matches in total: 
- Backend Detective: 2 matches
- Rapid Prototyping Engineer: 3 matches
- Developer Relations Lead: 6 matches
- Engineering Manager, Chaos Team: 6 matches
- Incident Commander: 5 matches
- Sales Engineer: 9 matches

---

## 5. Design decisions and trade-offs

**Weights (55 / 20 / 10 / 15).** Skills carry the most weight because a candidate without the required skills cannot do the job. Experience comes second because the assignment names it as a core factor. Culture and availability are deliberately lighter. They help separate otherwise similar candidates but should not outweigh ability. The weights are heuristic domain judgment, not tuned on real hiring outcomes. With outcome data I would fit them against actual historical placements.

**Zero skill overlap is excluded.** Without this gate, a candidate with no relevant skills could still score around 35 from experience and availability alone (for example Rick S. for Backend Detective). That is noise in a recruiter's list, so such pairs produce no match.

**Overqualification is not penalized.** Experience is capped at 1.0, so a 20-year candidate scores the same on experience as someone who just meets the minimum. This is a deliberate simplification. Penalizing seniority needs data about what the hiring team actually wants, and I did not want to invent it.

**`not_looking` candidates are still listed.** They lose all 15 availability points but remain visible, because a recruiter may still want to approach a strong passive candidate. The availability score and the reason text make their status clear.

**Matches are precomputed and stored.** Reads become an indexed lookup on `(job_id, score DESC, ...)` instead of scoring every pair on each request. The cost is staleness: stored scores go out of date when data or weights change. To handle that, every write (`POST /candidates`, `POST /jobs`, `POST /ingest`) recomputes the affected matches in the same transaction and removes stale rows. `POST /matches/recompute` rebuilds everything, for example after changing the weights.

**Raw SQL only.** All queries are hand-written and parameterized (`%s`) through `mysql-connector-python`, as the assignment requires. The schema is hand-written DDL in `db/migrations/001_init.sql`.

**Pure scoring function.** `app/services/scoring.py` does no database or network I/O. It takes plain data and returns a score and explanation, so it can be unit tested without a database.

**Synchronous endpoints.** The MySQL driver is blocking. Plain `def` handlers let FastAPI run them in its worker threadpool instead of blocking the async event loop.

**Input normalization.** Skills and traits are stripped and lowercased on ingestion, so inconsistent input cannot create duplicate skills.

### Known limitations

- Skills and traits are matched as exact strings. The only flexibility is a small alias map (`calm-under-pressure` matches the trait `calm`). There is no fuzzy or semantic matching.
- Skills are present or absent. There are no proficiency levels or recency.
- Weights are heuristic, not learned.
- Recomputation on write is simple and correct for this scale. At a much larger scale it should move to an asynchronous background job.

---

## 6. Project layout and database schema

```
app/
  main.py            FastAPI app, startup, error handling
  db.py              MySQL connection pool and transactions
  seed.py            Runs the migration and loads data/seed.json
  routers/           HTTP endpoints
  services/
    scoring.py       Pure scoring logic (no I/O)
    matching.py      Computes and stores matches
    ingestion.py     Loads candidates and jobs
  repositories/      Hand-written SQL
db/migrations/       001_init.sql (the DDL)
data/seed.json       The assignment's candidates and jobs
tests/               pytest tests
sql_detective.sql    Part 2
```

**Tables**

| Table | Purpose |
| :-- | :-- |
| `candidates` | name, years of experience, availability (`ENUM`), quirk |
| `jobs` | title, minimum experience, tagline |
| `skills`, `traits` | unique lookup values |
| `candidate_skills`, `candidate_traits` | candidate to skill/trait links |
| `job_required_skills`, `job_culture_keywords` | job to skill/keyword links |
| `matches` | stored result per `(job_id, candidate_id)`: total score, four sub-scores, matched and missing skills, reason |

`matches` has a composite primary key `(job_id, candidate_id)` and two ranking indexes, `(job_id, score DESC, candidate_id)` and `(candidate_id, score DESC, job_id)`, so both match endpoints read in order. Junction tables use `ON DELETE CASCADE`.

---

## 7. Tests

```bash
pytest -v
ruff check app tests
mypy app tests
```

- `tests/test_scoring.py`: pure scoring logic, including Sherlock vs Backend Detective = 95.0, the zero-overlap gate, experience capping, availability ordering, tie-breaking and the `calm` alias.
- `tests/test_api.py`: both match endpoints, pagination, `total`, 404 and 422 responses, recompute on write.
- `tests/test_ingestion.py`: seed loading and transaction rollback.

---

## 8. Part 2: SQL Detective

All five answers are in [`sql_detective.sql`](sql_detective.sql). The file creates the challenge tables and loads the seed data as given (not redesigned), then runs one query per question, each preceded by a `-- Q#` comment.

```bash
mysql -u <your_user> -p hiring_ops < sql_detective.sql
```

*(Create the `hiring_ops` database first if it does not exist.)*

| # | Question | Approach | Result |
| :-: | :-- | :-- | :-- |
| Q1 | Open postings with recruiter name | `JOIN` job postings to recruiters, `status = 'open'` | Jobs 1, 2, 4, 5 (Priya Shah, Daniel Ortiz, Priya Shah, Wei Zhang) |
| Q2 | Applicants who reached Final, per posting | `LEFT JOIN` so postings with none show 0; distinct by lowercased email | Job 1: 2, Job 2: 2, Job 3: 1, Job 4: 2, Job 5: 0, Job 6: 0, Job 7: 2 |
| Q3 | People who applied to more than one posting | Group by `LOWER(TRIM(email))`, `COUNT(DISTINCT job_posting_id) > 1`, which merges the two Ananya Rao rows | Ananya Rao (1, 4), Ben Turner (1, 3), Elena Popescu (2, 7) |
| Q4 | Final-stage conversion per recruiter (min. 3 Finals) | `HAVING COUNT(*) >= 3`, `1.0 *` to avoid integer division | Priya Shah 75.00%, Daniel Ortiz 50.00% |
| Q5 | Bonus: top recruiter per department by Final passes | `RANK() OVER (PARTITION BY department ORDER BY placements DESC)`, keep rank 1 | Engineering: Priya Shah (3), Data: Fatima Al-Sayed (1) |

**Q3 note:** the data is dirty. Applicants 1 and 2 are the same person with emails that differ only by capitalization, so grouping by the raw email or by applicant id would miss Ananya.

**Q5 note:** `RANK()` keeps ties, so if two recruiters tie for first in a department both appear. `ROW_NUMBER()` would pick one arbitrarily.

---

## 9. Use of AI tools

I used AI tools in two ways while working on this assignment:

- **Google Antigravity** (AI coding assistant): I used it to build the project code, including the FastAPI app, the raw SQL repositories, the scoring logic, the tests and the `sql_detective.sql` file.
- **Claude**: I used it to plan the approach, review the design and the requirements, and to write and edit the Markdown documentation (this README and the project guide).

I ran the app and the SQL queries locally, checked the outputs against the assignment data, and reviewed the code so I can explain the design and trade-offs in the follow-up conversation.
