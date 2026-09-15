-- Auth Service: Remove the admin account that earlier revisions of V1 seeded with a
-- fixed, publicly known password. Roles, refresh tokens and settings cascade.
-- A bootstrap admin is created at startup from AUTH_BOOTSTRAP_ADMIN_* instead.
DELETE FROM users
WHERE id = 'a0000000-0000-0000-0000-000000000001'
  AND email = 'admin@otterworks.dev';
