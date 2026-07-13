package com.otterworks.legacyportal.userpreferences;

import org.springframework.data.jpa.repository.JpaRepository;

public interface UserPreferenceRepository extends JpaRepository<UserPreference, String> {
}
