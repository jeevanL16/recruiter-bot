-- SQL Detective Schema
-- Database: hiring_ops

DROP TABLE IF EXISTS interviews;
DROP TABLE IF EXISTS applicants;
DROP TABLE IF EXISTS job_postings;
DROP TABLE IF EXISTS recruiters;

CREATE TABLE recruiters (
  id INT PRIMARY KEY,
  name VARCHAR(100),
  region VARCHAR(50)
);

CREATE TABLE job_postings (
  id INT PRIMARY KEY,
  title VARCHAR(100),
  recruiter_id INT,
  department VARCHAR(50),
  opened_date DATE,
  status VARCHAR(20) -- 'open', 'closed', 'on_hold'
);

CREATE TABLE applicants (
  id INT PRIMARY KEY,
  full_name VARCHAR(100),
  email VARCHAR(100),
  source VARCHAR(50), -- nullable
  applied_date DATE
);

CREATE TABLE interviews (
  id INT PRIMARY KEY,
  applicant_id INT,
  job_posting_id INT,
  stage VARCHAR(20),      -- 'Screen', 'Technical', 'Final'
  scheduled_date DATE,
  outcome VARCHAR(20)     -- 'passed', 'failed', 'no_show', NULL (pending)
);
