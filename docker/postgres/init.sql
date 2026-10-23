-- Runs once, on first start of an empty volume.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE DATABASE docflow_test OWNER docflow;
\connect docflow_test
CREATE EXTENSION IF NOT EXISTS vector;
