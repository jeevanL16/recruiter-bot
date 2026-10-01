# BUILD.md: Recruiter Bot + SQL Detective (Python + MySQL)

> Single source of truth for building the RecruiterFlow assignment. Work top to bottom. Every phase has a checklist and a "done when" condition.

---

## 0. Goals and Non-Negotiables

| Requirement from the brief | How this plan satisfies it |
|---|---|
| Any language | **Python 3.12** |
| Relational DB, **raw SQL only** (no ORM / query builder) | **MySQL 8** + `mysql-connector-python`, hand-written DDL and parameterised queries |
| Ingestion of candidates and jobs | Idempotent seed script **and** `POST /ingest` endpoint, driven by `data/seed.json` |
| Own schema (candidates, jobs, match) | Normalised schema + persisted `matches` table (section 3) |
| `GET /jobs/{id}/matches`, `GET /candidates/{id}/matches` | Both implemented, ranked, with score + short reason |
| Algorithm: skill overlap + experience fit | Weighted, explainable scoring, plus culture, availability, tie-breaks (section 5) |
| README with curl examples | Section 11 |
| Bonus: tests, API docs | pytest suite + auto OpenAPI at `/docs` |
| Part 2: single `.sql` file, one query per question, preceded by question-number comment | Section 9 (final answers included) |

**Quality bar (what "high quality" means here):**

- Type hints everywhere, `mypy --strict` clean, `ruff` clean.
- Zero string-formatted SQL. Every value is a bound parameter.
- Layered architecture: routers (HTTP) → services (logic) → repositories (SQL). The scoring function is **pure** (no I/O) and fully unit-tested.
- Deterministic ranking (explicit tie-breaks).
- Config via environment variables, structured logging, consistent error responses.
- One command to run everything (`docker compose up`).

---

## 1. Tech Stack

| Concern | Choice | Why |
|---|---|---|
| Web framework | **FastAPI** | Typed request/response models, free OpenAPI docs at `/docs` |
| DB driver | **mysql-connector-python** (official, with connection pooling) | Raw SQL, no abstraction layer |
| Validation | **Pydantic v2** + `pydantic-settings` | Typed config and API schemas (these do not generate SQL) |
| Server | **uvicorn** | Standard |
| Tests | **pytest**, `httpx` (FastAPI TestClient) | Unit + integration |
| Lint/type | **ruff**, **mypy** | Quality gates |
| Infra | **Docker Compose** (app + MySQL 8) | Reviewer runs it in one command |

Sync endpoints (`def`, not `async def`) are used on purpose: the connector is blocking, and FastAPI runs sync routes in a threadpool. Mixing a blocking driver into `async def` would stall the event loop. (Good interview talking point.)

---

## 2. Repository Layout

```
recruiter-bot/
├── BUILD.md
├── README.md
├── docker-compose.yml
├── Dockerfile
├── Makefile
├── pyproject.toml            # deps, ruff, mypy, pytest config
├── .env.example
├── .gitignore
├── data/
│   └── seed.json             # candidates + jobs (normalised)
├── db/
│   └── migrations/
│       └── 001_init.sql      # hand-written DDL
├── app/
│   ├── __init__.py
│   ├── main.py               # app factory, routers, exception handlers
│   ├── config.py             # Settings (env vars)
│   ├── db.py                 # pool, get_conn(), transaction() context manager
│   ├── migrate.py            # tiny migration runner (applies *.sql in order)
│   ├── logging_config.py
│   ├── errors.py             # NotFoundError, ValidationError -> HTTP mapping
│   ├── models.py             # dataclasses: Candidate, Job, ScoreBreakdown
│   ├── schemas.py            # Pydantic request/response models
│   ├── repositories/
│   │   ├── candidates.py     # all candidate SQL
│   │   ├── jobs.py           # all job SQL
│   │   └── matches.py        # all match SQL
│   ├── services/
│   │   ├── scoring.py        # PURE scoring functions (no DB)
│   │   ├── matching.py       # orchestrates recompute + reads
│   │   └── ingestion.py      # seed loading, upserts, normalisation
│   ├── routers/
│   │   ├── health.py
│   │   ├── ingest.py
│   │   ├── candidates.py
│   │   ├── jobs.py
│   │   └── matches.py
│   └── seed.py               # CLI: python -m app.seed
├── tests/
│   ├── conftest.py
│   ├── test_scoring.py       # pure unit tests
│   ├── test_ingestion.py
│   └── test_api.py           # integration against MySQL
└── sql_detective/
    ├── schema.sql            # given schema, loaded as-is
    ├── seed.sql              # given data, loaded as-is
    └── sql_detective.sql     # THE SUBMISSION FILE (answers)
```

---

## 3. Database Design (hand-written DDL)

### 3.1 Design decisions

1. **Normalise skills and traits** into lookup tables with join tables. This enables indexed overlap queries and avoids comma-separated columns.
2. **Candidate traits and job culture keywords share one `traits` vocabulary**, so culture matching is a join, not string parsing.
3. **Availability is an `ENUM`** (`immediate`, `two_weeks`, `not_looking`), so invalid values are impossible.
4. **Matches are persisted** in a `matches` table (see trade-off in section 3.3).
5. All names are normalised on write: lower-case, trimmed, kebab-case (`public-speaking`).
6. `utf8mb4`, InnoDB, FKs with `ON DELETE CASCADE`, `CHECK` constraints (enforced in MySQL 8.0.16+).

### 3.2 `db/migrations/001_init.sql`

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     VARCHAR(50) PRIMARY KEY,
    applied_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE skills (
    id    INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name  VARCHAR(64)  NOT NULL,
    UNIQUE KEY uq_skills_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE traits (
    id    INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name  VARCHAR(64)  NOT NULL,
    UNIQUE KEY uq_traits_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE candidates (
    id                INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    full_name         VARCHAR(100) NOT NULL,
    experience_years  DECIMAL(4,1) NOT NULL,
    availability      ENUM('immediate','two_weeks','not_looking') NOT NULL,
    quirk             VARCHAR(500) NULL,
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_candidates_full_name (full_name),
    CONSTRAINT ck_candidates_experience CHECK (experience_years >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE candidate_skills (
    candidate_id  INT UNSIGNED NOT NULL,
    skill_id      INT UNSIGNED NOT NULL,
    PRIMARY KEY (candidate_id, skill_id),
    KEY ix_candidate_skills_skill (skill_id),
    CONSTRAINT fk_cs_candidate FOREIGN KEY (candidate_id) REFERENCES candidates(id) ON DELETE CASCADE,
    CONSTRAINT fk_cs_skill     FOREIGN KEY (skill_id)     REFERENCES skills(id)     ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE candidate_traits (
    candidate_id  INT UNSIGNED NOT NULL,
    trait_id      INT UNSIGNED NOT NULL,
    PRIMARY KEY (candidate_id, trait_id),
    KEY ix_candidate_traits_trait (trait_id),
    CONSTRAINT fk_ct_candidate FOREIGN KEY (candidate_id) REFERENCES candidates(id) ON DELETE CASCADE,
    CONSTRAINT fk_ct_trait     FOREIGN KEY (trait_id)     REFERENCES traits(id)     ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE jobs (
    id                      INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    title                   VARCHAR(150) NOT NULL,
    min_experience_years    DECIMAL(4,1) NOT NULL,
    tagline                 VARCHAR(500) NULL,
    created_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_jobs_title (title),
    CONSTRAINT ck_jobs_min_exp CHECK (min_experience_years >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE job_required_skills (
    job_id    INT UNSIGNED NOT NULL,
    skill_id  INT UNSIGNED NOT NULL,
    PRIMARY KEY (job_id, skill_id),
    KEY ix_jrs_skill (skill_id),
    CONSTRAINT fk_jrs_job   FOREIGN KEY (job_id)   REFERENCES jobs(id)   ON DELETE CASCADE,
    CONSTRAINT fk_jrs_skill FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE job_culture_keywords (
    job_id    INT UNSIGNED NOT NULL,
    trait_id  INT UNSIGNED NOT NULL,
    PRIMARY KEY (job_id, trait_id),
    KEY ix_jck_trait (trait_id),
    CONSTRAINT fk_jck_job   FOREIGN KEY (job_id)   REFERENCES jobs(id)   ON DELETE CASCADE,
    CONSTRAINT fk_jck_trait FOREIGN KEY (trait_id) REFERENCES traits(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- A "match" = a scored (job, candidate) pair, stored with its full breakdown
CREATE TABLE matches (
    job_id              INT UNSIGNED  NOT NULL,
    candidate_id        INT UNSIGNED  NOT NULL,
    score               DECIMAL(5,2)  NOT NULL,   -- 0.00 .. 100.00
    skill_score         DECIMAL(4,3)  NOT NULL,   -- 0..1
    experience_score    DECIMAL(4,3)  NOT NULL,
    culture_score       DECIMAL(4,3)  NOT NULL,
    availability_score  DECIMAL(4,3)  NOT NULL,
    matched_skills      JSON          NOT NULL,
    missing_skills      JSON          NOT NULL,
    reason              VARCHAR(500)  NOT NULL,
    scoring_version     VARCHAR(20)   NOT NULL,
    computed_at         TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (job_id, candidate_id),
    KEY ix_matches_job_rank       (job_id, score DESC, candidate_id),
    KEY ix_matches_candidate_rank (candidate_id, score DESC, job_id),
    CONSTRAINT fk_m_job       FOREIGN KEY (job_id)       REFERENCES jobs(id)       ON DELETE CASCADE,
    CONSTRAINT fk_m_candidate FOREIGN KEY (candidate_id) REFERENCES candidates(id) ON DELETE CASCADE,
    CONSTRAINT ck_matches_score CHECK (score BETWEEN 0 AND 100)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 3.3 Trade-off: persisted vs. computed-on-read matches

| | Persisted `matches` (chosen) | Compute on every request |
|---|---|---|
| Read latency | Index range scan, O(k) | O(candidates x skills) per call |
| Explainability/audit | Breakdown and reason stored; `scoring_version` allows A/B | Gone after response |
| Staleness | Must recompute on data change | Always fresh |
| Complexity | Needs recompute hooks | Simpler |

**Chosen mitigation:** recompute is triggered **inside the same transaction** as any write (ingest/create/update/delete candidate or job). A job change recomputes that job's row-set. A candidate change recomputes that candidate's row-set. `POST /matches/recompute` rebuilds everything. For a 15x6 dataset this is instant. At scale it moves to a background worker (mention in README "Future work").

---

## 4. Seed Data (`data/seed.json`)

The assignment PDF has broken line wraps (`public-speaki ng`). Normalise as below. Availability `"Not looking"` maps to `not_looking`, `"2 weeks"` to `two_weeks`.

```json
{
  "candidates": [
    {"full_name":"Sherlock H.","skills":["deduction","pattern-recognition","forensics"],"experience_years":8,"availability":"immediate","traits":["analytical","blunt"],"quirk":"Solves problems by eliminating the impossible; occasionally insufferable in standups."},
    {"full_name":"Hermione G.","skills":["research","time-management","public-speaking"],"experience_years":4,"availability":"two_weeks","traits":["detail-oriented","overachiever"],"quirk":"Reads the entire documentation before writing a single line of code."},
    {"full_name":"Tony S.","skills":["systems-design","rapid-prototyping","leadership"],"experience_years":12,"availability":"not_looking","traits":["confident","innovative"],"quirk":"Ships an MVP overnight, refuses to write tests."},
    {"full_name":"Leslie K.","skills":["project-management","stakeholder-management","public-speaking"],"experience_years":6,"availability":"immediate","traits":["tenacious","organized"],"quirk":"Has a binder for everything, including the binder."},
    {"full_name":"Ron S.","skills":["woodworking","minimalism","negotiation"],"experience_years":15,"availability":"not_looking","traits":["stubborn","principled"],"quirk":"Refuses to use more than one monitor."},
    {"full_name":"Rick S.","skills":["systems-design","rapid-prototyping","chemistry"],"experience_years":20,"availability":"immediate","traits":["genius","reckless"],"quirk":"Solution works, mechanism deeply concerning."},
    {"full_name":"Elle W.","skills":["persuasion","research","public-speaking"],"experience_years":3,"availability":"immediate","traits":["optimistic","sharp"],"quirk":"Underestimated in every standup, correct in every retro."},
    {"full_name":"MacGyver","skills":["rapid-prototyping","resourcefulness","chemistry","systems-design"],"experience_years":10,"availability":"two_weeks","traits":["calm","improviser"],"quirk":"Fixes production outages with duct tape and a paperclip metaphor."},
    {"full_name":"Sheldon C.","skills":["theoretical-analysis","pattern-recognition","research"],"experience_years":9,"availability":"immediate","traits":["rigid","brilliant"],"quirk":"Correct 95% of the time, insufferable 100% of the time."},
    {"full_name":"Katniss E.","skills":["precision","strategy","crisis-management"],"experience_years":5,"availability":"immediate","traits":["resilient","decisive"],"quirk":"Excellent under pressure, terrible with public speaking."},
    {"full_name":"Michael S.","skills":["sales","public-speaking","team-building"],"experience_years":11,"availability":"not_looking","traits":["enthusiastic","chaotic"],"quirk":"World's best boss, according to a mug he bought himself."},
    {"full_name":"Olivia P.","skills":["crisis-management","negotiation","strategy","leadership"],"experience_years":13,"availability":"two_weeks","traits":["decisive","intense"],"quirk":"Handles it. Whatever it is."},
    {"full_name":"Ted L.","skills":["team-building","optimism","mentorship","public-speaking"],"experience_years":7,"availability":"immediate","traits":["empathetic","persistent"],"quirk":"Turns every technical setback into a folksy metaphor."},
    {"full_name":"Miranda P.","skills":["leadership","negotiation","stakeholder-management","precision"],"experience_years":18,"availability":"not_looking","traits":["demanding","decisive"],"quirk":"Reviews every PR personally. Says nothing. Everyone panics."},
    {"full_name":"Dwight S.","skills":["sales","negotiation","security","loyalty"],"experience_years":9,"availability":"immediate","traits":["intense","loyal"],"quirk":"Assistant to the regional backend engineer."}
  ],
  "jobs": [
    {"title":"Backend Detective","required_skills":["deduction","pattern-recognition","forensics"],"min_experience_years":3,"culture_keywords":["analytical","autonomous"],"tagline":"We have a bug. We have no leads. We have you."},
    {"title":"Rapid Prototyping Engineer","required_skills":["rapid-prototyping","systems-design"],"min_experience_years":2,"culture_keywords":["innovative","fast-paced"],"tagline":"Ship first, document never (kidding, please document)."},
    {"title":"Developer Relations Lead","required_skills":["public-speaking","research"],"min_experience_years":2,"culture_keywords":["energetic","curious"],"tagline":"Explain complex things to confused humans, cheerfully."},
    {"title":"Engineering Manager, Chaos Team","required_skills":["team-building","stakeholder-management","leadership"],"min_experience_years":5,"culture_keywords":["empathetic","organized"],"tagline":"Herd cats. The cats are senior engineers."},
    {"title":"Incident Commander","required_skills":["crisis-management","strategy","negotiation"],"min_experience_years":4,"culture_keywords":["decisive","calm-under-pressure"],"tagline":"3am page. You're the one who picks up."},
    {"title":"Sales Engineer","required_skills":["sales","public-speaking","negotiation"],"min_experience_years":3,"culture_keywords":["enthusiastic","persistent"],"tagline":"Sell the vision, then go build it."}
  ]
}
```

**Ingestion behaviour (`services/ingestion.py`):**

- Idempotent upsert: `INSERT ... ON DUPLICATE KEY UPDATE` keyed on `candidates.full_name` and `jobs.title`.
- Skills/traits: `INSERT IGNORE` into lookup tables, then resolve ids with `SELECT id, name FROM skills WHERE name IN (...)` (parameter list built with `%s` placeholders only).
- Link tables: replace sets by deleting rows not in the new set, then `INSERT IGNORE` the rest.
- Whole payload runs in **one transaction**. On any error it rolls back, leaving no partial state.
- After commit (inside the same transaction), run recompute. Return counts: `{"candidates": 15, "jobs": 6, "matches": 90}`.
- Entry points: `python -m app.seed` and `POST /ingest` (body = same JSON shape; no body = load `data/seed.json`).

---

## 5. Matching Algorithm (the heart)

### 5.1 Components (each normalised to 0..1)

**a) Skill coverage (weight 0.55).** The job defines requirements, so measure how much of them the candidate covers. This is recall-oriented, not Jaccard, because extra skills should not penalise a candidate.

```
skill_score = |candidate_skills ∩ required_skills| / |required_skills|
```

**b) Experience fit (weight 0.20).** Three zones:

```
min = job.min_experience_years, exp = candidate.experience_years
upper = max(2 * min, min + 5)        # "sweet spot" ceiling

exp < min          -> exp / min                          # proportional shortfall
min <= exp <= upper -> 1.0
exp > upper        -> 1 - min(0.30, 0.02 * (exp - upper)) # gentle over-qualification decay, floor 0.70
```

Rationale: under-qualified is a real gap. Over-qualified is a retention/cost risk, but never disqualifying, hence the 0.70 floor.

**c) Culture fit (weight 0.10).** Overlap of the candidate's traits with the job's culture keywords, optionally with a small alias map in config (e.g. `calm-under-pressure -> calm`):

```
culture_score = |traits ∩ culture_keywords| / |culture_keywords|
```

Low weight because traits are soft, self-reported signals that rarely match keywords exactly.

**d) Availability (weight 0.15).** `immediate = 1.0`, `two_weeks = 0.7`, `not_looking = 0.0`. Passive candidates are not excluded. Recruiters still want to know about them. They are ranked lower and flagged in the reason.

### 5.2 Final score

```
raw   = 0.55*skill + 0.20*experience + 0.10*culture + 0.15*availability
score = round(raw * 100, 2)
```

### 5.3 Eligibility gates and tie-breaks

- **Gate:** skip pairs with `skill_score == 0`. A match with zero skill overlap is noise. Also skip `score < MIN_SCORE` (default 20, configurable via the `min_score` query param).
- **Deterministic ordering:** `score DESC, skill_score DESC, availability_score DESC, candidate_id ASC` (and `job_id ASC` in the reverse direction).
- **What is deliberately ignored:** names and the `quirk` field. Quirks are flavour text, so using them would be arbitrary and unexplainable.

### 5.4 Reason string (short, human-readable)

Built from the breakdown, e.g.:

> `Covers 3/3 required skills (deduction, pattern-recognition, forensics); 8 yrs vs 3 min; culture: analytical; available immediately.`
> `Covers 2/3 required skills; missing: public-speaking; 9 yrs vs 3 min (over-qualified); not currently looking.`

### 5.5 Expected sanity results (use as test assertions)

| Job | Expected top result | Why |
|---|---|---|
| Backend Detective | **Sherlock H.** (~95) | 3/3 skills, experience in sweet spot, culture match, immediate |
| Rapid Prototyping Engineer | **Rick S.** (~84.8), then **MacGyver** (~84.3), then **Tony S.** (~78) | All have both skills. Over-qualification decay and availability separate them |
| Incident Commander | **Olivia P.** (3/3 skills) above Katniss (2/3) | Skill coverage dominates |
| Sales Engineer | **Dwight S.** (2/3 skills, immediate) above Michael S. (2/3, not looking) | Availability breaks the skill tie |

Exact decimals may shift if you tune weights. Assert **ordering**, not floats.

### 5.6 Defending the design (interview prep)

- **Why weighted sum, not ML?** Tiny dataset, no labels, and recruiters need explainability. Every point of the score traces to a component.
- **Why skills heaviest?** Hard requirement of the job. Experience is a proxy; culture and availability are tiebreaker-grade.
- **Why not hard-exclude not-looking?** Passive candidates are valuable; exposing them with a low-ranked flag is more useful than hiding them.
- **Why recall, not Jaccard?** Jaccard punishes candidates who know more than the job requires.
- **Known limitations:** exact string skill matching (no synonyms/embeddings), equal skill weighting (a "must-have" vs "nice-to-have" split would be the next step), culture exact-match only.
- **Next steps:** weighted/required-vs-preferred skills, skill taxonomy/aliases, background recompute worker, pagination cursors, feedback loop to tune weights.

---

## 6. API Specification

Base URL `http://localhost:8000`. JSON everywhere. OpenAPI docs at `/docs`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness and DB ping |
| POST | `/ingest` | Load seed (or posted payload), idempotent |
| POST | `/matches/recompute` | Rebuild all matches |
| GET | `/candidates` / `/candidates/{id}` | List / fetch |
| POST | `/candidates` | Create (and auto-score) |
| GET | `/jobs` / `/jobs/{id}` | List / fetch |
| POST | `/jobs` | Create (and auto-score) |
| **GET** | **`/jobs/{id}/matches`** | **Ranked candidates for a job** |
| **GET** | **`/candidates/{id}/matches`** | **Ranked jobs for a candidate** |

**Match query params:** `limit` (default 10, max 100), `offset` (default 0), `min_score` (default 0), `availability` (optional filter: `immediate|two_weeks|not_looking`, only on the job endpoint).

**Response, `GET /jobs/1/matches`:**

```json
{
  "job": {"id": 1, "title": "Backend Detective", "min_experience_years": 3.0},
  "total": 3,
  "limit": 10,
  "offset": 0,
  "matches": [
    {
      "rank": 1,
      "candidate": {"id": 1, "full_name": "Sherlock H.", "experience_years": 8.0, "availability": "immediate"},
      "score": 95.0,
      "breakdown": {"skills": 1.0, "experience": 1.0, "culture": 0.5, "availability": 1.0},
      "matched_skills": ["deduction", "forensics", "pattern-recognition"],
      "missing_skills": [],
      "reason": "Covers 3/3 required skills (deduction, forensics, pattern-recognition); 8 yrs vs 3 min; culture: analytical; available immediately."
    }
  ]
}
```

**Errors (uniform shape):** `{"error": {"code": "not_found", "message": "Job 99 not found"}}`

- `404` unknown id, `422` invalid input/params, `500` unexpected (logged with traceback, generic message to the client).
- A job/candidate that exists but has no matches returns `200` with `"matches": []`, **not** 404.

---

## 7. Implementation Details

### 7.1 `app/db.py`

- Create one `MySQLConnectionPool` (size from config) at startup.
- `get_conn()` is a FastAPI dependency that yields a pooled connection and always closes (returns to the pool) in `finally`.
- `transaction(conn)` context manager: `conn.start_transaction()`, commit on success, rollback on exception.
- Always `cursor(dictionary=True)`. Never build SQL with f-strings or `%` formatting. Dynamic `IN (...)` lists are built as `",".join(["%s"] * n)` of **placeholders only**.

### 7.2 Repository rule

All SQL lives in `repositories/*.py` as module-level constant strings. Services and routers contain **no SQL**. One function per query, documented, typed.

Key queries (examples to hand-write):

```sql
-- candidates with their skills/traits, in 3 round trips total (avoids N+1)
SELECT id, full_name, experience_years, availability FROM candidates;
SELECT cs.candidate_id, s.name FROM candidate_skills cs JOIN skills s ON s.id = cs.skill_id;
SELECT ct.candidate_id, t.name FROM candidate_traits ct JOIN traits t ON t.id = ct.trait_id;

-- ranked matches for a job (page + total)
SELECT c.id, c.full_name, c.experience_years, c.availability,
       m.score, m.skill_score, m.experience_score, m.culture_score, m.availability_score,
       m.matched_skills, m.missing_skills, m.reason
FROM matches m
JOIN candidates c ON c.id = m.candidate_id
WHERE m.job_id = %s AND m.score >= %s
ORDER BY m.score DESC, m.skill_score DESC, m.availability_score DESC, c.id ASC
LIMIT %s OFFSET %s;

-- bulk write
INSERT INTO matches (job_id, candidate_id, score, skill_score, experience_score,
                     culture_score, availability_score, matched_skills, missing_skills,
                     reason, scoring_version)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);   -- executemany
```

### 7.3 `services/scoring.py` (pure)

```python
@dataclass(frozen=True, slots=True)
class CandidateProfile:
    id: int
    skills: frozenset[str]
    traits: frozenset[str]
    experience_years: float
    availability: Availability


@dataclass(frozen=True, slots=True)
class JobProfile:
    id: int
    required_skills: frozenset[str]
    culture_keywords: frozenset[str]
    min_experience_years: float


@dataclass(frozen=True, slots=True)
class ScoreResult:
    score: float
    skills: float
    experience: float
    culture: float
    availability: float
    matched: tuple[str, ...]
    missing: tuple[str, ...]
    reason: str


def score_pair(
    candidate: CandidateProfile, job: JobProfile, weights: Weights = DEFAULT_WEIGHTS
) -> ScoreResult | None: ...
```

- Weights live in a frozen `Weights` dataclass (validated to sum to 1.0), configurable from env, versioned via `SCORING_VERSION = "v1"`.
- Handle `min_experience_years == 0` (avoid divide-by-zero: experience score = 1.0) and empty `required_skills` (job is unscoreable, so return no matches rather than crash).
- Sort `matched`/`missing` alphabetically so output is deterministic.

### 7.4 `services/matching.py`

- `recompute_all(conn)`: load candidates and jobs (3+3 queries), score the full cross product in memory, `DELETE FROM matches`, `executemany` insert, all in one transaction.
- `recompute_for_job(conn, job_id)` / `recompute_for_candidate(conn, candidate_id)`: delete that slice and re-insert.
- `get_job_matches(...)` / `get_candidate_matches(...)`: raise `NotFoundError` if the parent does not exist, otherwise read from `matches`.

### 7.5 Cross-cutting

- **Logging:** JSON or key=value logs, request id per request, log recompute durations and counts.
- **Config (`.env.example`):** `DB_HOST DB_PORT DB_USER DB_PASSWORD DB_NAME DB_POOL_SIZE MIN_SCORE_DEFAULT SCORING_WEIGHTS LOG_LEVEL`
- **Security basics:** parameterised SQL only, no secrets in repo, DB user with least privilege in compose, request-size limit on `/ingest`.
- **Migrations:** `app/migrate.py` runs on startup, applies unapplied `db/migrations/*.sql` in order, and records versions in `schema_migrations`. Split statements safely (no semicolons inside strings in this schema).

---

## 8. Testing Plan

**Unit (`test_scoring.py`, no DB, fast):**

- Full skill coverage = 1.0, partial = n/m, none = 0 (and `score_pair` returns `None`).
- Experience: below min (proportional), at min (1.0), inside the sweet spot (1.0), above upper (decay), the 0.70 floor, `min=0`.
- Availability mapping for all three values.
- Culture overlap, including alias handling.
- Weights sum to 1.0 (validation error otherwise).
- Tie-break determinism: equal scores order by the documented keys.
- Reason string contains matched/missing skills and the availability phrase.

**Integration (`test_api.py`, real MySQL via compose):**

- `POST /ingest` twice gives the same row counts (idempotent).
- Section 5.5 ordering assertions (Sherlock top for Backend Detective, etc.).
- `GET /candidates/{id}/matches` is the mirror of the job endpoint (same score for the same pair).
- 404 for unknown ids, `200` + empty list for no matches, `422` for bad `limit`.
- Create a new candidate via the API, then appears in the relevant job match list (recompute hook works).
- Rollback test: a malformed ingest payload leaves tables unchanged.

**Quality gates (`make check`):** `ruff check .`, `ruff format --check .`, `mypy --strict app`, `pytest -q`.

---

## 9. Part 2: SQL Detective (final answers)

Load **as-is** into a separate database (`hiring_ops`), no redesign: `sql_detective/schema.sql` (the given DDL) and `sql_detective/seed.sql` (the given inserts). Submit `sql_detective.sql` below (MySQL 8 syntax, window functions need 8.0+).

**Data traps to call out in the README:**

- Applicants 1 and 2 are the same person (`Ananya Rao`; email differs only in case; different source/date). A naive `GROUP BY applicant_id` misses her.
- There is **no applications table**; "applied to a job" can only be inferred from `interviews`. State this assumption.
- Some interview chains skip stages (e.g. applicant 3 has a Final for job 3 without earlier stages). Do not assume a clean funnel.
- `NULL` source and `NULL` outcome exist; `no_show` counts as a Final-stage interview only if its stage is Final (none here).

```sql
-- sql_detective.sql  (MySQL 8.0+)

-- Q1: All currently open job postings with the owning recruiter's name
SELECT jp.id            AS job_posting_id,
       jp.title,
       jp.department,
       jp.opened_date,
       r.name           AS recruiter_name
FROM job_postings AS jp
JOIN recruiters   AS r ON r.id = jp.recruiter_id
WHERE jp.status = 'open'
ORDER BY jp.id;
-- Expected: postings 1, 2, 4, 5

-- Q2: For each job posting, how many applicants reached the Final stage
-- Counts distinct PEOPLE (normalised email), keeps postings with zero via LEFT JOIN.
SELECT jp.id    AS job_posting_id,
       jp.title,
       COUNT(DISTINCT LOWER(TRIM(a.email))) AS applicants_reached_final
FROM job_postings AS jp
LEFT JOIN interviews AS i
       ON i.job_posting_id = jp.id
      AND i.stage = 'Final'
LEFT JOIN applicants AS a
       ON a.id = i.applicant_id
GROUP BY jp.id, jp.title
ORDER BY jp.id;
-- Expected: 1->2, 2->2, 3->1, 4->2, 5->0, 6->0, 7->2

-- Q3: People who effectively applied to more than one job posting
-- Dedupe identity by normalised email (Ananya Rao exists twice with different email casing).
-- "Applied" is inferred from having an interview for the posting (no applications table exists).
SELECT LOWER(TRIM(a.email))               AS person_email,
       MIN(a.full_name)                   AS full_name,
       COUNT(DISTINCT i.job_posting_id)   AS postings_applied_to,
       GROUP_CONCAT(DISTINCT i.job_posting_id ORDER BY i.job_posting_id) AS posting_ids
FROM applicants AS a
JOIN interviews AS i ON i.applicant_id = a.id
GROUP BY LOWER(TRIM(a.email))
HAVING COUNT(DISTINCT i.job_posting_id) > 1
ORDER BY full_name;
-- Expected: Ananya Rao (1,4), Ben Turner (1,3), Elena Popescu (2,7)

-- Q4: Final-stage conversion rate per recruiter (min. 3 Final-stage interviews)
SELECT r.id   AS recruiter_id,
       r.name AS recruiter_name,
       COUNT(*)                                             AS final_interviews,
       SUM(CASE WHEN i.outcome = 'passed' THEN 1 ELSE 0 END) AS passed,
       ROUND(100 * SUM(CASE WHEN i.outcome = 'passed' THEN 1 ELSE 0 END) / COUNT(*), 2)
                                                            AS conversion_rate_pct
FROM recruiters   AS r
JOIN job_postings AS jp ON jp.recruiter_id = r.id
JOIN interviews   AS i  ON i.job_posting_id = jp.id
                       AND i.stage = 'Final'
GROUP BY r.id, r.name
HAVING COUNT(*) >= 3
ORDER BY conversion_rate_pct DESC, r.id;
-- Expected: Priya Shah 3/4 = 75.00 ; Daniel Ortiz 2/4 = 50.00
-- (Fatima Al-Sayed has only 1 Final, so she is excluded by HAVING)

-- Q5 (Bonus): Recruiter with the most successful placements (Final passed) per department
-- Window function RANK() so ties are all returned.
WITH placements AS (
    SELECT jp.department,
           r.id   AS recruiter_id,
           r.name AS recruiter_name,
           COUNT(*) AS placements
    FROM interviews   AS i
    JOIN job_postings AS jp ON jp.id = i.job_posting_id
    JOIN recruiters   AS r  ON r.id  = jp.recruiter_id
    WHERE i.stage = 'Final' AND i.outcome = 'passed'
    GROUP BY jp.department, r.id, r.name
),
ranked AS (
    SELECT p.*,
           RANK() OVER (PARTITION BY p.department ORDER BY p.placements DESC) AS rnk
    FROM placements AS p
)
SELECT department, recruiter_name, placements
FROM ranked
WHERE rnk = 1
ORDER BY department;
-- Expected: Data -> Fatima Al-Sayed (1) ; Engineering -> Priya Shah (3)
-- (Infrastructure has no placements, so it does not appear)
```

---

## 10. Build Phases (checklist)

**Phase 1: Foundation (≈1 hr)**
- [ ] `git init`, `pyproject.toml`, `ruff`/`mypy`/`pytest` config, `.gitignore`, `.env.example`
- [ ] `docker-compose.yml` (MySQL 8 with healthcheck + app), `Dockerfile`
- [ ] `config.py`, `logging_config.py`, `db.py`, `errors.py`
- [ ] `migrate.py` + `001_init.sql`: tables created on startup
- *Done when:* `docker compose up` starts, `/health` returns DB ok.

**Phase 2: Ingestion (≈1 hr)**
- [ ] `data/seed.json` (section 4)
- [ ] Repositories for candidates/jobs with upserts
- [ ] `ingestion.py` (normalisation + one transaction) + `python -m app.seed` + `POST /ingest`
- *Done when:* running seed twice leaves 15 candidates / 6 jobs.

**Phase 3: Scoring (≈1.5 hr)**
- [ ] `scoring.py` (pure) + `test_scoring.py` written **first** (TDD)
- [ ] `matching.py`: recompute + `matches` repository
- *Done when:* unit tests green; ordering in section 5.5 holds.

**Phase 4: API (≈1 hr)**
- [ ] The two required match endpoints + pagination/filters
- [ ] CRUD (create/get/list) with recompute hooks
- [ ] Error handlers, response schemas
- *Done when:* every curl in the README works.

**Phase 5: Part 2 SQL (≈45 min)**
- [ ] Load `schema.sql` + `seed.sql` into `hiring_ops`, run each query, and verify against the "Expected" comments
- [ ] Save as `sql_detective.sql` (one query per question, preceded by `-- Qn` comment)

**Phase 6: Polish (≈1 hr)**
- [ ] Integration tests, `make check` passes
- [ ] README (setup, curl examples, design decisions, trade-offs, limitations)
- [ ] Fresh-clone test: `git clone` into a new folder, then `docker compose up`, then run curls

---

## 11. README Content Plan

1. One-paragraph overview and architecture diagram (routers → services → repositories → MySQL).
2. Quick start: `cp .env.example .env && docker compose up --build`, then `docker compose exec app python -m app.seed`.
3. curl examples:

```bash
curl -s localhost:8000/health
curl -s -X POST localhost:8000/ingest
curl -s "localhost:8000/jobs/1/matches?limit=5"
curl -s "localhost:8000/candidates/1/matches"
curl -s "localhost:8000/jobs/2/matches?availability=immediate&min_score=50"
curl -s -X POST localhost:8000/matches/recompute
```

4. Schema summary and the persisted-matches rationale.
5. Scoring formula with weights and the reasoning in section 5.6.
6. Assumptions (Part 2 "applied" inferred from interviews; email-based identity).
7. Running tests, `make check`.
8. Known limitations and future work.

**`Makefile` targets:** `up`, `down`, `seed`, `test`, `lint`, `typecheck`, `check`.

---

## 12. Final Submission Checklist

- [ ] No ORM or query builder anywhere (`grep -ri "sqlalchemy\|peewee\|orm" .` returns nothing)
- [ ] No f-string SQL: `grep -rn 'f"SELECT\|f"INSERT\|f"UPDATE\|f"DELETE'` returns nothing
- [ ] Both required endpoints return rank, score, and a reason
- [ ] Algorithm accounts for skill overlap **and** experience fit (plus the extras you can defend)
- [ ] `sql_detective.sql` has all 5 queries, each with a `-- Qn` comment
- [ ] Tests pass and `make check` is green
- [ ] README has curl examples and an explanation of trade-offs
- [ ] Repo has a clean commit history (small, meaningful commits)
- [ ] Notes ready for the walkthrough: persisted vs. on-read matches, scoring weights, over-qualification decay, passive-candidate handling, sync-vs-async choice, what you would do next