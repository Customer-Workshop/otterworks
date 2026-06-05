-- Rotate the seed admin password hash to remove the hardcoded value from V1.
-- The new password is read from the ADMIN_SEED_PASSWORD Flyway placeholder
-- (defaults to the same dev password so existing environments keep working).
CREATE EXTENSION IF NOT EXISTS pgcrypto;

UPDATE users
SET password_hash = crypt('${admin_seed_password}', gen_salt('bf', 12)),
    updated_at   = NOW()
WHERE id = 'a0000000-0000-0000-0000-000000000001';
