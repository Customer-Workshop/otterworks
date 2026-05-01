package com.otterworks.auth.controller;

import com.otterworks.auth.dto.UserSettingsDTO;
import com.otterworks.auth.entity.UserSettings;
import com.otterworks.auth.repository.UserSettingsRepository;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/settings")
public class SettingsController {

  private final UserSettingsRepository settingsRepository;

  public SettingsController(UserSettingsRepository settingsRepository) {
    this.settingsRepository = settingsRepository;
  }

  @GetMapping
  public ResponseEntity<UserSettingsDTO> getSettings(Authentication authentication) {
    UUID userId = UUID.fromString((String) authentication.getPrincipal());
    UserSettingsDTO dto =
        settingsRepository
            .findById(userId)
            .map(UserSettingsDTO::fromEntity)
            .orElse(UserSettingsDTO.defaults());
    return ResponseEntity.ok(dto);
  }

  @PatchMapping
  public ResponseEntity<UserSettingsDTO> updateSettings(
      Authentication authentication, @RequestBody UserSettingsDTO request) {
    UUID userId = UUID.fromString((String) authentication.getPrincipal());
    UserSettings settings =
        settingsRepository.findById(userId).orElseGet(() -> {
          UserSettings s = new UserSettings();
          s.setUserId(userId);
          return s;
        });

    if (request.getTheme() != null) {
      settings.setTheme(request.getTheme());
    }
    if (request.getLanguage() != null) {
      settings.setLanguage(request.getLanguage());
    }
    settings.setNotificationEmail(request.isNotificationEmail());
    settings.setNotificationInApp(request.isNotificationInApp());
    settings.setNotificationDesktop(request.isNotificationDesktop());

    settings = settingsRepository.save(settings);
    return ResponseEntity.ok(UserSettingsDTO.fromEntity(settings));
  }
}
