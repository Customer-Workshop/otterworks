-- Auth Service: User management schema
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    avatar_url VARCHAR(500),
    email_verified BOOLEAN NOT NULL DEFAULT false,
    mfa_enabled BOOLEAN NOT NULL DEFAULT false,
    mfa_secret VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS user_roles (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL,
    PRIMARY KEY (user_id, role)
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_created_at ON users(created_at);

-- Seed admin user. The password hash is supplied at migration time via the
-- seed_admin_password_hash Flyway placeholder, derived from AUTH_SEED_ADMIN_PASSWORD
-- (local-dev default set in docker-compose.yml). When unset the account is seeded with
-- an unusable random password.
INSERT INTO users (id, email, password_hash, display_name, email_verified, created_at, updated_at)
VALUES (
    'a0000000-0000-0000-0000-000000000001',
    'admin@otterworks.dev',
    '${seed_admin_password_hash}',
    'Admin User',
    true,
    NOW(),
    NOW()
);

INSERT INTO user_roles (user_id, role) VALUES
('a0000000-0000-0000-0000-000000000001', 'ADMIN'),
('a0000000-0000-0000-0000-000000000001', 'USER');
