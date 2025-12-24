-- K0 PostgreSQL Initialization Script
-- Part of Milestone 1.1.1 - PostgreSQL Infrastructure
--
-- This script runs on first container startup to create:
-- 1. The k0user application user (database already created via POSTGRES_DB)
-- 2. Required permissions

-- Create the application user (if not exists)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'k0user') THEN
        CREATE USER k0user WITH ENCRYPTED PASSWORD 'changeme';
    END IF;
END $$;

-- Grant privileges on the database
GRANT ALL PRIVILEGES ON DATABASE k0_kernel TO k0user;

-- Grant schema privileges (already connected to k0_kernel via POSTGRES_DB)
GRANT ALL ON SCHEMA public TO k0user;
GRANT CREATE ON SCHEMA public TO k0user;

-- Set default privileges for future objects
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT ALL ON TABLES TO k0user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT ALL ON SEQUENCES TO k0user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT EXECUTE ON FUNCTIONS TO k0user;

-- Create a comment for documentation
COMMENT ON DATABASE k0_kernel IS 'K0 Kernel runtime database - FamilyOS intelligence kernel';
