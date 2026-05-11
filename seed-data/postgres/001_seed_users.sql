-- OtterWorks Seed Data: Users & Roles
-- Populates the auth-service Postgres database with otter-themed engineering org members.
-- All passwords are bcrypt hash of 'OtterPass1!' for development use only.
-- nosemgrep: generic.secrets.security.detected-bcrypt-hash.detected-bcrypt-hash

-- Password hash for 'OtterPass1!'
-- $2a$10$rQXBc4K7yC6Zz1YdR7.8qOJkZv3yF5Qm8pN1xL2wA4sE6hT0gUiW

INSERT INTO users (id, email, password_hash, display_name, avatar_url, email_verified, mfa_enabled, created_at, updated_at, last_login_at) VALUES
-- The Lodge (Engineering)
('b0000000-0000-0000-0000-000000000001', 'ollie.lutris@otterworks.io', '$2a$10$rQXBc4K7yC6Zz1YdR7.8qOJkZv3yF5Qm8pN1xL2wA4sE6hT0gUiW', 'Ollie Lutris', NULL, true, false, '2025-01-10 08:00:00+00', '2026-05-10 09:30:00+00', '2026-05-10 09:30:00+00'),
('b0000000-0000-0000-0000-000000000002', 'marina.enhydra@otterworks.io', '$2a$10$rQXBc4K7yC6Zz1YdR7.8qOJkZv3yF5Qm8pN1xL2wA4sE6hT0gUiW', 'Marina Enhydra', NULL, true, true, '2025-01-15 10:00:00+00', '2026-05-11 08:15:00+00', '2026-05-11 08:15:00+00'),
('b0000000-0000-0000-0000-000000000003', 'finn.aonyx@otterworks.io', '$2a$10$rQXBc4K7yC6Zz1YdR7.8qOJkZv3yF5Qm8pN1xL2wA4sE6hT0gUiW', 'Finn Aonyx', NULL, true, false, '2025-02-01 09:00:00+00', '2026-05-09 17:45:00+00', '2026-05-09 17:45:00+00'),
('b0000000-0000-0000-0000-000000000004', 'river.canadensis@otterworks.io', '$2a$10$rQXBc4K7yC6Zz1YdR7.8qOJkZv3yF5Qm8pN1xL2wA4sE6hT0gUiW', 'River Canadensis', NULL, true, false, '2025-02-20 11:00:00+00', '2026-05-10 14:20:00+00', '2026-05-10 14:20:00+00'),
('b0000000-0000-0000-0000-000000000005', 'brook.cinerea@otterworks.io', '$2a$10$rQXBc4K7yC6Zz1YdR7.8qOJkZv3yF5Qm8pN1xL2wA4sE6hT0gUiW', 'Brook Cinerea', NULL, true, false, '2025-03-05 08:30:00+00', '2026-05-08 16:00:00+00', '2026-05-08 16:00:00+00'),
-- The Raft (Product)
('b0000000-0000-0000-0000-000000000006', 'kelp.perspicillata@otterworks.io', '$2a$10$rQXBc4K7yC6Zz1YdR7.8qOJkZv3yF5Qm8pN1xL2wA4sE6hT0gUiW', 'Kelp Perspicillata', NULL, true, false, '2025-01-20 09:00:00+00', '2026-05-11 07:50:00+00', '2026-05-11 07:50:00+00'),
('b0000000-0000-0000-0000-000000000007', 'pebble.sumatrana@otterworks.io', '$2a$10$rQXBc4K7yC6Zz1YdR7.8qOJkZv3yF5Qm8pN1xL2wA4sE6hT0gUiW', 'Pebble Sumatrana', NULL, true, false, '2025-03-15 10:30:00+00', '2026-05-10 11:00:00+00', '2026-05-10 11:00:00+00'),
('b0000000-0000-0000-0000-000000000008', 'cascade.felina@otterworks.io', '$2a$10$rQXBc4K7yC6Zz1YdR7.8qOJkZv3yF5Qm8pN1xL2wA4sE6hT0gUiW', 'Cascade Felina', NULL, true, false, '2025-04-01 08:00:00+00', '2026-05-09 15:30:00+00', '2026-05-09 15:30:00+00'),
-- The Den (Design)
('b0000000-0000-0000-0000-000000000009', 'coral.maculicollis@otterworks.io', '$2a$10$rQXBc4K7yC6Zz1YdR7.8qOJkZv3yF5Qm8pN1xL2wA4sE6hT0gUiW', 'Coral Maculicollis', NULL, true, false, '2025-02-10 09:00:00+00', '2026-05-10 10:45:00+00', '2026-05-10 10:45:00+00'),
('b0000000-0000-0000-0000-000000000010', 'shell.brasiliensis@otterworks.io', '$2a$10$rQXBc4K7yC6Zz1YdR7.8qOJkZv3yF5Qm8pN1xL2wA4sE6hT0gUiW', 'Shell Brasiliensis', NULL, true, false, '2025-03-25 10:00:00+00', '2026-05-07 13:20:00+00', '2026-05-07 13:20:00+00'),
-- The Stream (Data)
('b0000000-0000-0000-0000-000000000011', 'delta.provocax@otterworks.io', '$2a$10$rQXBc4K7yC6Zz1YdR7.8qOJkZv3yF5Qm8pN1xL2wA4sE6hT0gUiW', 'Delta Provocax', NULL, true, false, '2025-01-25 08:00:00+00', '2026-05-11 06:30:00+00', '2026-05-11 06:30:00+00'),
('b0000000-0000-0000-0000-000000000012', 'rapids.longicaudis@otterworks.io', '$2a$10$rQXBc4K7yC6Zz1YdR7.8qOJkZv3yF5Qm8pN1xL2wA4sE6hT0gUiW', 'Rapids Longicaudis', NULL, true, false, '2025-04-10 09:00:00+00', '2026-05-10 08:00:00+00', '2026-05-10 08:00:00+00'),
-- The Burrow (DevOps / Platform)
('b0000000-0000-0000-0000-000000000013', 'dam.sanfilippo@otterworks.io', '$2a$10$rQXBc4K7yC6Zz1YdR7.8qOJkZv3yF5Qm8pN1xL2wA4sE6hT0gUiW', 'Dam Sanfilippo', NULL, true, true, '2025-01-05 07:00:00+00', '2026-05-11 05:45:00+00', '2026-05-11 05:45:00+00'),
('b0000000-0000-0000-0000-000000000014', 'tide.platensis@otterworks.io', '$2a$10$rQXBc4K7yC6Zz1YdR7.8qOJkZv3yF5Qm8pN1xL2wA4sE6hT0gUiW', 'Tide Platensis', NULL, true, false, '2025-02-15 08:30:00+00', '2026-05-10 16:10:00+00', '2026-05-10 16:10:00+00'),
('b0000000-0000-0000-0000-000000000015', 'eddy.vittata@otterworks.io', '$2a$10$rQXBc4K7yC6Zz1YdR7.8qOJkZv3yF5Qm8pN1xL2wA4sE6hT0gUiW', 'Eddy Vittata', NULL, true, false, '2025-05-01 09:00:00+00', '2026-05-09 12:30:00+00', '2026-05-09 12:30:00+00'),
-- The Cove (Security)
('b0000000-0000-0000-0000-000000000016', 'riptide.giant@otterworks.io', '$2a$10$rQXBc4K7yC6Zz1YdR7.8qOJkZv3yF5Qm8pN1xL2wA4sE6hT0gUiW', 'Riptide Giant', NULL, true, true, '2025-01-12 08:00:00+00', '2026-05-11 09:00:00+00', '2026-05-11 09:00:00+00'),
('b0000000-0000-0000-0000-000000000017', 'surf.indica@otterworks.io', '$2a$10$rQXBc4K7yC6Zz1YdR7.8qOJkZv3yF5Qm8pN1xL2wA4sE6hT0gUiW', 'Surf Indica', NULL, true, false, '2025-03-20 10:00:00+00', '2026-05-10 07:45:00+00', '2026-05-10 07:45:00+00'),
-- Additional engineers (The Lodge)
('b0000000-0000-0000-0000-000000000018', 'reed.lataxina@otterworks.io', '$2a$10$rQXBc4K7yC6Zz1YdR7.8qOJkZv3yF5Qm8pN1xL2wA4sE6hT0gUiW', 'Reed Lataxina', NULL, true, false, '2025-04-15 09:30:00+00', '2026-05-08 18:00:00+00', '2026-05-08 18:00:00+00'),
('b0000000-0000-0000-0000-000000000019', 'cove.maxima@otterworks.io', '$2a$10$rQXBc4K7yC6Zz1YdR7.8qOJkZv3yF5Qm8pN1xL2wA4sE6hT0gUiW', 'Cove Maxima', NULL, true, false, '2025-05-10 08:00:00+00', '2026-05-09 11:15:00+00', '2026-05-09 11:15:00+00'),
('b0000000-0000-0000-0000-000000000020', 'marsh.lutra@otterworks.io', '$2a$10$rQXBc4K7yC6Zz1YdR7.8qOJkZv3yF5Qm8pN1xL2wA4sE6hT0gUiW', 'Marsh Lutra', NULL, true, false, '2025-06-01 10:00:00+00', '2026-05-10 13:50:00+00', '2026-05-10 13:50:00+00'),
-- Interns & contractors
('b0000000-0000-0000-0000-000000000021', 'splash.minor@otterworks.io', '$2a$10$rQXBc4K7yC6Zz1YdR7.8qOJkZv3yF5Qm8pN1xL2wA4sE6hT0gUiW', 'Splash Minor', NULL, true, false, '2025-09-01 08:00:00+00', '2026-05-06 10:00:00+00', '2026-05-06 10:00:00+00'),
('b0000000-0000-0000-0000-000000000022', 'wade.nair@otterworks.io', '$2a$10$rQXBc4K7yC6Zz1YdR7.8qOJkZv3yF5Qm8pN1xL2wA4sE6hT0gUiW', 'Wade Nair', NULL, false, false, '2026-01-15 09:00:00+00', '2026-05-10 08:30:00+00', '2026-05-10 08:30:00+00'),
('b0000000-0000-0000-0000-000000000023', 'bay.smooth@otterworks.io', '$2a$10$rQXBc4K7yC6Zz1YdR7.8qOJkZv3yF5Qm8pN1xL2wA4sE6hT0gUiW', 'Bay Smooth-Coated', NULL, true, false, '2025-07-20 08:00:00+00', '2026-05-09 09:00:00+00', '2026-05-09 09:00:00+00'),
-- Leadership
('b0000000-0000-0000-0000-000000000024', 'harbor.giant@otterworks.io', '$2a$10$rQXBc4K7yC6Zz1YdR7.8qOJkZv3yF5Qm8pN1xL2wA4sE6hT0gUiW', 'Harbor Giant', NULL, true, true, '2024-06-01 08:00:00+00', '2026-05-11 10:00:00+00', '2026-05-11 10:00:00+00'),
('b0000000-0000-0000-0000-000000000025', 'estuary.atlas@otterworks.io', '$2a$10$rQXBc4K7yC6Zz1YdR7.8qOJkZv3yF5Qm8pN1xL2wA4sE6hT0gUiW', 'Estuary Atlas', NULL, true, true, '2024-06-15 09:00:00+00', '2026-05-11 08:45:00+00', '2026-05-11 08:45:00+00')
ON CONFLICT (email) DO NOTHING;

-- Roles
INSERT INTO user_roles (user_id, role) VALUES
-- Admins
('b0000000-0000-0000-0000-000000000001', 'ADMIN'), ('b0000000-0000-0000-0000-000000000001', 'USER'),
('b0000000-0000-0000-0000-000000000013', 'ADMIN'), ('b0000000-0000-0000-0000-000000000013', 'USER'),
('b0000000-0000-0000-0000-000000000024', 'ADMIN'), ('b0000000-0000-0000-0000-000000000024', 'USER'),
('b0000000-0000-0000-0000-000000000025', 'ADMIN'), ('b0000000-0000-0000-0000-000000000025', 'USER'),
-- Regular users
('b0000000-0000-0000-0000-000000000002', 'USER'),
('b0000000-0000-0000-0000-000000000003', 'USER'),
('b0000000-0000-0000-0000-000000000004', 'USER'),
('b0000000-0000-0000-0000-000000000005', 'USER'),
('b0000000-0000-0000-0000-000000000006', 'USER'),
('b0000000-0000-0000-0000-000000000007', 'USER'),
('b0000000-0000-0000-0000-000000000008', 'USER'),
('b0000000-0000-0000-0000-000000000009', 'USER'),
('b0000000-0000-0000-0000-000000000010', 'USER'),
('b0000000-0000-0000-0000-000000000011', 'USER'),
('b0000000-0000-0000-0000-000000000012', 'USER'),
('b0000000-0000-0000-0000-000000000014', 'USER'),
('b0000000-0000-0000-0000-000000000015', 'USER'),
('b0000000-0000-0000-0000-000000000016', 'USER'),
('b0000000-0000-0000-0000-000000000017', 'USER'),
('b0000000-0000-0000-0000-000000000018', 'USER'),
('b0000000-0000-0000-0000-000000000019', 'USER'),
('b0000000-0000-0000-0000-000000000020', 'USER'),
('b0000000-0000-0000-0000-000000000021', 'USER'),
('b0000000-0000-0000-0000-000000000022', 'USER'),
('b0000000-0000-0000-0000-000000000023', 'USER')
ON CONFLICT DO NOTHING;
