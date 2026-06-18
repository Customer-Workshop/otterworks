-- Replace the well-known seed password hash with a configurable placeholder.
-- The actual hash is supplied via Flyway placeholder ${admin_password_hash},
-- configured in application.yml and overridable via environment variable.
UPDATE users
SET password_hash = '${admin_password_hash}',
    updated_at = NOW()
WHERE id = 'a0000000-0000-0000-0000-000000000001';
