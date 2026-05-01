package com.otterworks.auth.repository;

import com.otterworks.auth.entity.UserSettings;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface UserSettingsRepository extends JpaRepository<UserSettings, UUID> {}
