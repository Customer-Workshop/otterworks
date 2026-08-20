package com.otterworks.portal.userpreferences;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/**
 * Keyed by the caller-supplied natural key; no surrogate id. The monolith's
 * {@code user_preferences} schema qualifier is dropped because the database is dedicated.
 */
@Entity
@Table(name = "user_preference")
public class UserPreference {

    @Id
    @Column(name = "user_id", length = 100)
    private String userId;

    @Column(nullable = false, length = 20)
    private String theme;

    @Column(nullable = false, length = 20)
    private String locale;

    @Column(name = "email_notifications", nullable = false)
    private boolean emailNotifications;

    protected UserPreference() {
        // JPA
    }

    public UserPreference(String userId, String theme, String locale, boolean emailNotifications) {
        this.userId = userId;
        this.theme = theme;
        this.locale = locale;
        this.emailNotifications = emailNotifications;
    }

    public String getUserId() {
        return userId;
    }

    public String getTheme() {
        return theme;
    }

    public void setTheme(String theme) {
        this.theme = theme;
    }

    public String getLocale() {
        return locale;
    }

    public void setLocale(String locale) {
        this.locale = locale;
    }

    public boolean isEmailNotifications() {
        return emailNotifications;
    }

    public void setEmailNotifications(boolean emailNotifications) {
        this.emailNotifications = emailNotifications;
    }
}
