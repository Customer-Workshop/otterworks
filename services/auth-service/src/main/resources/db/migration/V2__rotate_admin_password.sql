-- Rotate the seed admin password to remove the committed hash from V1.
-- The application should enforce a password-change on first login.
UPDATE users
SET password_hash = '$2b$12$MAdXvQPz4Sk2CSP8ygnDWeIbRdr.gpNdYlJi.29fiTogToEjrnGU.',
    updated_at = NOW()
WHERE id = 'a0000000-0000-0000-0000-000000000001';
