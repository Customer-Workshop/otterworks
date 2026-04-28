-- Auth Service: Roles reference table
CREATE TABLE IF NOT EXISTS roles (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    description VARCHAR(255)
);

INSERT INTO roles (name, description) VALUES
('USER', 'Standard user with basic access'),
('EDITOR', 'Can create and edit documents'),
('ADMIN', 'Full administrative access'),
('OWNER', 'Organization owner with all permissions');
