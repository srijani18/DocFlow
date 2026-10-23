-- Runs once, on first start of an empty volume.
-- Only the test database is created here. Extensions and schemas come from migrations,
-- exactly as on Supabase (ADR-0007).
CREATE DATABASE docflow_test OWNER docflow;
