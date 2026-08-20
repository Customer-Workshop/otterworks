-- Revoke the seeded admin password hash that was previously committed in V1 on databases
-- that already applied it. The replacement comes from the seed_admin_password_hash Flyway
-- placeholder (AUTH_SEED_ADMIN_PASSWORD; unusable random password when unset).
UPDATE users
SET password_hash = '${seed_admin_password_hash}',
    updated_at = NOW()
WHERE id = 'a0000000-0000-0000-0000-000000000001';
