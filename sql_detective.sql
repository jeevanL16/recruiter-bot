-- ============================================================================
-- SQL Detective Challenge
-- Database Dialect: MySQL 8.0+
--
-- This file is self-contained: it creates the schema, inserts seed data,
-- and then runs 5 investigative queries. Run it inside a database named
-- hiring_ops (or any empty database).
--
-- To run:  mysql -u root -p hiring_ops < sql_detective.sql
-- ============================================================================


-- ============================================================================
-- SECTION 1: SCHEMA
-- ============================================================================

DROP TABLE IF EXISTS interviews;
DROP TABLE IF EXISTS applicants;
DROP TABLE IF EXISTS job_postings;
DROP TABLE IF EXISTS recruiters;

CREATE TABLE recruiters (
    id     INT PRIMARY KEY,
    name   VARCHAR(100),
    region VARCHAR(50)
);

CREATE TABLE job_postings (
    id           INT PRIMARY KEY,
    title        VARCHAR(100),
    recruiter_id INT,
    department   VARCHAR(50),
    opened_date  DATE,
    status       VARCHAR(20)
);

CREATE TABLE applicants (
    id           INT PRIMARY KEY,
    full_name    VARCHAR(100),
    email        VARCHAR(100),
    source       VARCHAR(50),
    applied_date DATE
);

CREATE TABLE interviews (
    id              INT PRIMARY KEY,
    applicant_id    INT,
    job_posting_id  INT,
    stage           VARCHAR(20),
    scheduled_date  DATE,
    outcome         VARCHAR(20)
);


-- ============================================================================
-- SECTION 2: SEED DATA (copied exactly from the assignment)
-- ============================================================================

INSERT INTO recruiters (id, name, region) VALUES
    (1,'Priya Shah','APAC'),
    (2,'Daniel Ortiz','NA'),
    (3,'Fatima Al-Sayed','EMEA'),
    (4,'Wei Zhang','APAC'),
    (5,'Grace Okafor','EMEA');

INSERT INTO job_postings (id, title, recruiter_id, department, opened_date, status) VALUES
    (1,'Backend Engineer I',1,'Engineering','2026-01-05','open'),
    (2,'Backend Engineer I',2,'Engineering','2026-01-10','open'),
    (3,'Data Analyst',3,'Data','2026-01-08','closed'),
    (4,'Backend Engineer II',1,'Engineering','2026-02-01','open'),
    (5,'DevOps Engineer',4,'Infrastructure','2026-01-20','open'),
    (6,'Data Analyst',5,'Data','2026-02-05','on_hold'),
    (7,'Backend Engineer I',2,'Engineering','2026-02-15','closed');

INSERT INTO applicants (id, full_name, email, source, applied_date) VALUES
    (1,'Ananya Rao','ananya.rao@mail.com','LinkedIn','2026-01-06'),
    (2,'Ananya Rao','Ananya.Rao@mail.com','Referral','2026-02-04'),
    (3,'Ben Turner','ben.turner@mail.com','Job Board','2026-01-07'),
    (4,'Chloe Martin','chloe.martin@mail.com',NULL,'2026-01-09'),
    (5,'Devansh Patel','devansh.patel@mail.com','LinkedIn','2026-01-11'),
    (6,'Elena Popescu','elena.popescu@mail.com','Referral','2026-01-12'),
    (7,'Farid Haidari','farid.haidari@mail.com','Job Board','2026-01-13'),
    (8,'Grace Lin','grace.lin@mail.com','LinkedIn','2026-01-15'),
    (9,'Hassan Malik','hassan.malik@mail.com',NULL,'2026-01-16'),
    (10,'Isla Fraser','isla.fraser@mail.com','Referral','2026-01-18'),
    (11,'Jonas Weber','jonas.weber@mail.com','Job Board','2026-02-10');

INSERT INTO interviews (id, applicant_id, job_posting_id, stage, scheduled_date, outcome) VALUES
    (1,1,1,'Screen','2026-01-10','passed'),
    (2,1,1,'Technical','2026-01-15','passed'),
    (3,1,1,'Final','2026-01-22','passed'),
    (4,2,4,'Screen','2026-02-05','passed'),
    (5,3,1,'Screen','2026-01-11','passed'),
    (6,3,1,'Technical','2026-01-16','failed'),
    (7,3,3,'Final','2026-01-28','passed'),
    (8,4,1,'Screen','2026-01-12','passed'),
    (9,4,1,'Final','2026-01-24','failed'),
    (10,5,2,'Screen','2026-01-14','passed'),
    (11,5,2,'Technical','2026-01-19','passed'),
    (12,5,2,'Final','2026-01-25','passed'),
    (13,6,2,'Screen','2026-01-15','passed'),
    (14,6,2,'Final','2026-01-26','failed'),
    (15,7,2,'Screen','2026-01-16','no_show'),
    (16,8,4,'Screen','2026-02-03','passed'),
    (17,8,4,'Technical','2026-02-08','passed'),
    (18,8,4,'Final','2026-02-12','passed'),
    (19,9,4,'Screen','2026-02-04','passed'),
    (20,9,4,'Final','2026-02-14','passed'),
    (21,10,5,'Screen','2026-01-22','passed'),
    (22,10,5,'Technical','2026-01-28',NULL),
    (23,11,7,'Final','2026-02-20','passed'),
    (24,6,7,'Final','2026-02-21','failed');


-- ============================================================================
-- SECTION 3: QUERIES
-- ============================================================================


-- Q1: All currently open job postings with the recruiter's name.
-- Expected: jobs 1, 2, 4, 5.
SELECT jp.id            AS job_posting_id,
       jp.title,
       jp.department,
       jp.opened_date,
       r.name           AS recruiter_name
FROM job_postings AS jp
JOIN recruiters   AS r ON r.id = jp.recruiter_id
WHERE jp.status = 'open'
ORDER BY jp.id;


-- Q2: For each job posting, how many applicants reached the Final stage.
-- LEFT JOIN ensures jobs with zero Final-stage applicants still show 0.
-- Applicants are counted by normalised email (LOWER(TRIM(email))) so the
-- duplicate Ananya Rao rows are not double-counted.
-- Expected: job1=2, job2=2, job3=1, job4=2, job5=0, job6=0, job7=2.
SELECT jp.id                                AS job_posting_id,
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


-- Q3: People who effectively applied to more than one job posting.
-- The data is dirty: Ananya Rao has two applicant rows (ids 1 and 2) whose
-- emails differ only by capitalisation. We group by LOWER(TRIM(email)) and
-- link to job postings through the interviews table.
-- Expected: Ananya Rao (jobs 1,4), Ben Turner (jobs 1,3), Elena Popescu (jobs 2,7).
SELECT LOWER(TRIM(a.email))               AS person_email,
       MIN(a.full_name)                   AS full_name,
       COUNT(DISTINCT i.job_posting_id)   AS postings_applied_to,
       GROUP_CONCAT(DISTINCT i.job_posting_id ORDER BY i.job_posting_id) AS posting_ids
FROM applicants AS a
JOIN interviews AS i ON i.applicant_id = a.id
GROUP BY LOWER(TRIM(a.email))
HAVING COUNT(DISTINCT i.job_posting_id) > 1
ORDER BY person_email;


-- Q4: Per recruiter, Final-stage conversion rate (passed Finals / total Finals).
-- Only recruiters with at least 3 Final-stage interviews (HAVING).
-- We avoid integer division by multiplying by 1.0 and round to 2 decimals.
-- Expected: Priya Shah 3/4 = 75.00%, Daniel Ortiz 2/4 = 50.00%.
SELECT r.name                                                           AS recruiter_name,
       COUNT(*)                                                         AS total_finals,
       SUM(CASE WHEN i.outcome = 'passed' THEN 1 ELSE 0 END)           AS passed_finals,
       ROUND(1.0 * SUM(CASE WHEN i.outcome = 'passed' THEN 1 ELSE 0 END)
             / COUNT(*) * 100, 2)                                       AS conversion_rate_pct
FROM interviews   AS i
JOIN job_postings AS jp ON jp.id = i.job_posting_id
JOIN recruiters   AS r  ON r.id = jp.recruiter_id
WHERE i.stage = 'Final'
GROUP BY r.id, r.name
HAVING COUNT(*) >= 3
ORDER BY conversion_rate_pct DESC;


-- Q5 (Bonus): Recruiter with the most successful placements per department.
-- A "successful placement" is a passed Final-stage interview.
-- We use RANK() OVER (PARTITION BY department ORDER BY placements DESC)
-- so that tied recruiters both appear at rank 1. ROW_NUMBER() would
-- arbitrarily pick one, which is undesirable for a fairness report.
-- Expected: Engineering -> Priya Shah (3), Data -> Fatima Al-Sayed (1).
SELECT department,
       recruiter_name,
       placements
FROM (
    SELECT jp.department,
           r.name                                                      AS recruiter_name,
           SUM(CASE WHEN i.outcome = 'passed' THEN 1 ELSE 0 END)      AS placements,
           RANK() OVER (
               PARTITION BY jp.department
               ORDER BY SUM(CASE WHEN i.outcome = 'passed' THEN 1 ELSE 0 END) DESC
           ) AS rnk
    FROM interviews   AS i
    JOIN job_postings AS jp ON jp.id = i.job_posting_id
    JOIN recruiters   AS r  ON r.id = jp.recruiter_id
    WHERE i.stage = 'Final'
    GROUP BY jp.department, r.id, r.name
) AS ranked
WHERE rnk = 1
ORDER BY department;
