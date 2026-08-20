CREATE TABLE user_preference (
    user_id             VARCHAR(100) PRIMARY KEY,
    theme               VARCHAR(20)  NOT NULL,
    locale              VARCHAR(20)  NOT NULL,
    email_notifications BOOLEAN      NOT NULL
);
