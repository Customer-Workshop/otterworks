-- Revoke the previously committed seed admin password. Only the leaked hash is
-- locked (matched by its SHA-256 fingerprint so the hash itself is not committed);
-- a password rotated through the API is left in place. '!' is not a valid bcrypt
-- hash, so a locked account stays locked until AdminBootstrap sets a hash from
-- AUTH_BOOTSTRAP_ADMIN_PASSWORD at startup.
UPDATE users
SET password_hash = '!', updated_at = NOW()
WHERE id = 'a0000000-0000-0000-0000-000000000001'
  AND encode(sha256(convert_to(password_hash, 'UTF8')), 'hex')
      = '06456ebb89a24e2fb0a01f4e5f02254664a0859c377fc00b650e8f20f55372d5';
