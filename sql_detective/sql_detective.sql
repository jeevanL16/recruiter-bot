-- ============================================================================
-- SQL Detective Challenge - Submission File
-- Database Dialect: MySQL 8.0+
-- 
-- Key Assumptions and Edge Cases Documented:
-- 1. Identity Normalisation: Applicants 1 & 2 represent the same individual
--    (Ananya Rao) whose email differs only by casing ('ananya.rao@mail.com' vs
--    'Ananya.Rao@mail.com'). Queries 2 and 3 normalise via LOWER(TRIM(email))
--    to prevent duplicate counting.
-- 2. Applications Table Assumption: No dedicated 'applications' table exists.
--    Job applications are inferred from the existence of interview records.
-- 3. Non-Linear Stages: Candidates may enter at later stages without preceding
--    Screen/Technical interviews (e.g. Applicant 3 entered at Final for Job 3).
-- 4. Incomplete/Pending Outcomes: NULL outcomes and 'no_show' values are handled
--    defensively in aggregates.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- Q1: All currently open job postings with the owning recruiter's name
-- ----------------------------------------------------------------------------
SELECT jp.id            AS job_posting_id,
       jp.title,
       jp.department,
       jp.opened_date,
       r.name           AS recruiter_name
FROM job_postings AS jp
JOIN recruiters   AS r ON r.id = jp.recruiter_id
WHERE jp.status = 'open'
ORDER BY jp.id;


-- ----------------------------------------------------------------------------
-- Q2: For each job posting, how many applicants reached the Final stage
-- ----------------------------------------------------------------------------
-- Counts distinct people (normalised email) to avoid double-counting if an
-- applicant had multiple interview attempts. LEFT JOIN ensures postings with
-- 0 Final-stage applicants are retained.
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


-- ----------------------------------------------------------------------------
-- Q3: People who effectively applied to more than one job posting
-- ----------------------------------------------------------------------------
-- Deduplicates person identity by normalised email (Ananya Rao exists twice).
-- An application is inferred from an interview record for that posting.
SELECT LOWER(TRIM(a.email))               AS person_email,
       MIN(a.full_name)                   AS full_name,
       COUNT(DISTINCT i.job_posting_id)   AS postings_applied_to,
       GROUP_CONCAT(DISTINCT i.job_posting_id ORDER BY i.job_posting_id) AS posting_ids
FROM applicants AS a
JOIN interviews AS i ON i.applicant_id = a.id
GROUP BY LOWER(TRIM(a.email))
HAVING COUNT(DISTINCT i.job_posting_id) > 1
ORDER BY full_name;


-- ----------------------------------------------------------------------------
-- Q4: Final-stage conversion rate per recruiter (min. 3 Final-stage interviews)
-- ----------------------------------------------------------------------------
-- Conversion rate = (passed at Final stage / total Final-stage interviews).
-- Filtered to recruiters with at least 3 Final-stage interviews via HAVING.
SELECT r.id                                                  AS recruiter_id,
       r.name                                                AS recruiter_name,
       COUNT(*)                                              AS final_interviews,
       SUM(CASE WHEN i.outcome = 'passed' THEN 1 ELSE 0 END) AS passed,
       ROUND(
           100.0 * SUM(CASE WHEN i.outcome = 'passed' THEN 1 ELSE 0 END) / COUNT(*),
           2
       )                                                     AS conversion_rate_pct
FROM recruiters   AS r
JOIN job_postings AS jp ON jp.recruiter_id = r.id
JOIN interviews   AS i  ON i.job_posting_id = jp.id
                       AND i.stage = 'Final'
GROUP BY r.id, r.name
HAVING COUNT(*) >= 3
ORDER BY conversion_rate_pct DESC, r.id;


-- ----------------------------------------------------------------------------
-- Q5 (Bonus): Recruiter with the most successful placements per department
-- ----------------------------------------------------------------------------
-- Uses the window function RANK() partitioned by department to handle any ties
-- gracefully. Placements are defined as candidates who passed the Final stage.
WITH placements AS (
    SELECT jp.department,
           r.id     AS recruiter_id,
           r.name   AS recruiter_name,
           COUNT(*) AS placements
    FROM interviews   AS i
    JOIN job_postings AS jp ON jp.id = i.job_posting_id
    JOIN recruiters   AS r  ON r.id  = jp.recruiter_id
    WHERE i.stage = 'Final'
      AND i.outcome = 'passed'
    GROUP BY jp.department, r.id, r.name
),
ranked AS (
    SELECT p.department,
           p.recruiter_name,
           p.placements,
           RANK() OVER (PARTITION BY p.department ORDER BY p.placements DESC) AS rnk
    FROM placements AS p
)
SELECT department,
       recruiter_name,
       placements
FROM ranked
WHERE rnk = 1
ORDER BY department;
