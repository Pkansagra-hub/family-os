# K0 PostgreSQL 16 with pgvector extension
# Part of Milestone 1.1.1 - PostgreSQL Infrastructure
# Using pgvector/pgvector image which includes pgvector pre-installed
FROM pgvector/pgvector:pg16

# Copy initialization scripts (executed in alphabetical order)
COPY init.sql /docker-entrypoint-initdb.d/01-init.sql
COPY extensions.sql /docker-entrypoint-initdb.d/02-extensions.sql

# Health check
HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
    CMD pg_isready -U k0user -d k0_kernel || exit 1

# Default port
EXPOSE 5432
