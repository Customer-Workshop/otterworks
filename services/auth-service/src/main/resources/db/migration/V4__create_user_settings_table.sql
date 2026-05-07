CREATE TABLE IF NOT EXISTS user_settings (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    notification_email BOOLEAN NOT NULL DEFAULT true,
    notification_in_app BOOLEAN NOT NULL DEFAULT true,
    notification_desktop BOOLEAN NOT NULL DEFAULT false,
    theme VARCHAR(10) NOT NULL DEFAULT 'system',
    language VARCHAR(10) NOT NULL DEFAULT 'en'
);
