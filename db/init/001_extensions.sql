-- Runs automatically the first time the Postgres container starts.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Tables for employees, teams, tickets and documents are added in week 1.
