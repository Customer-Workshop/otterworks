-- Revoke the previously committed seed admin password. '!' is not a valid bcrypt
-- hash, so the account stays locked until AdminBootstrap sets a hash from
-- AUTH_BOOTSTRAP_ADMIN_PASSWORD at startup.
UPDATE users
SET password_hash = '!', updated_at = NOW()
WHERE id = 'a0000000-0000-0000-0000-000000000001';
