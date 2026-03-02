-- PostgreSQL initialization script for pygwire functional tests
-- This creates the test schema and tables used by the proxy_functional test suite

-- Create test schema
CREATE SCHEMA IF NOT EXISTS test_schema;

-- Simple table for basic queries, transactions, extended queries
CREATE TABLE IF NOT EXISTS test_schema.simple_table (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    value INTEGER
);

-- Table for COPY protocol tests
CREATE TABLE IF NOT EXISTS test_schema.copy_test (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    amount NUMERIC(10, 2)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_simple_table_value ON test_schema.simple_table(value);
CREATE INDEX IF NOT EXISTS idx_copy_test_name ON test_schema.copy_test(name);

-- Initial test data (tests will reset this)
INSERT INTO test_schema.simple_table (name, value) VALUES
    ('Alice', 100),
    ('Bob', 200),
    ('Charlie', 300);

-- Create test users for authentication tests
-- Note: Set password_encryption to ensure correct password storage method
CREATE USER trust_user;

-- MD5 user (legacy method)
SET password_encryption = 'md5';
CREATE USER md5_user WITH PASSWORD 'md5pass';

-- SCRAM-SHA-256 user (modern method, required for PG 13+)
SET password_encryption = 'scram-sha-256';
CREATE USER scram_user WITH PASSWORD 'scrampass';

-- Grant permissions to test users
GRANT ALL PRIVILEGES ON SCHEMA test_schema TO trust_user, md5_user, scram_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA test_schema TO trust_user, md5_user, scram_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA test_schema TO trust_user, md5_user, scram_user;

-- Default postgres user permissions
GRANT ALL PRIVILEGES ON SCHEMA test_schema TO postgres;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA test_schema TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA test_schema TO postgres;
