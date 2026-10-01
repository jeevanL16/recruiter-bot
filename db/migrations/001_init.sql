CREATE TABLE IF NOT EXISTS schema_migrations (
    version     VARCHAR(50) PRIMARY KEY,
    applied_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS skills (
    id    INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name  VARCHAR(64)  NOT NULL,
    UNIQUE KEY uq_skills_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS traits (
    id    INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name  VARCHAR(64)  NOT NULL,
    UNIQUE KEY uq_traits_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS candidates (
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

CREATE TABLE IF NOT EXISTS candidate_skills (
    candidate_id  INT UNSIGNED NOT NULL,
    skill_id      INT UNSIGNED NOT NULL,
    PRIMARY KEY (candidate_id, skill_id),
    KEY ix_candidate_skills_skill (skill_id),
    CONSTRAINT fk_cs_candidate FOREIGN KEY (candidate_id) REFERENCES candidates(id) ON DELETE CASCADE,
    CONSTRAINT fk_cs_skill     FOREIGN KEY (skill_id)     REFERENCES skills(id)     ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS candidate_traits (
    candidate_id  INT UNSIGNED NOT NULL,
    trait_id      INT UNSIGNED NOT NULL,
    PRIMARY KEY (candidate_id, trait_id),
    KEY ix_candidate_traits_trait (trait_id),
    CONSTRAINT fk_ct_candidate FOREIGN KEY (candidate_id) REFERENCES candidates(id) ON DELETE CASCADE,
    CONSTRAINT fk_ct_trait     FOREIGN KEY (trait_id)     REFERENCES traits(id)     ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS jobs (
    id                      INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    title                   VARCHAR(150) NOT NULL,
    min_experience_years    DECIMAL(4,1) NOT NULL,
    tagline                 VARCHAR(500) NULL,
    created_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_jobs_title (title),
    CONSTRAINT ck_jobs_min_exp CHECK (min_experience_years >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS job_required_skills (
    job_id    INT UNSIGNED NOT NULL,
    skill_id  INT UNSIGNED NOT NULL,
    PRIMARY KEY (job_id, skill_id),
    KEY ix_jrs_skill (skill_id),
    CONSTRAINT fk_jrs_job   FOREIGN KEY (job_id)   REFERENCES jobs(id)   ON DELETE CASCADE,
    CONSTRAINT fk_jrs_skill FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS job_culture_keywords (
    job_id    INT UNSIGNED NOT NULL,
    trait_id  INT UNSIGNED NOT NULL,
    PRIMARY KEY (job_id, trait_id),
    KEY ix_jck_trait (trait_id),
    CONSTRAINT fk_jck_job   FOREIGN KEY (job_id)   REFERENCES jobs(id)   ON DELETE CASCADE,
    CONSTRAINT fk_jck_trait FOREIGN KEY (trait_id) REFERENCES traits(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS matches (
    job_id              INT UNSIGNED  NOT NULL,
    candidate_id        INT UNSIGNED  NOT NULL,
    score               DECIMAL(5,2)  NOT NULL,
    skill_score         DECIMAL(4,3)  NOT NULL,
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
