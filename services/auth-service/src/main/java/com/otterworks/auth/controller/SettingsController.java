package com.otterworks.auth.controller;

import com.otterworks.auth.dto.UpdateSettingsRequest;
import com.otterworks.auth.dto.UserSettingsDTO;
import com.otterworks.auth.service.UserSettingsService;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/settings")
public class SettingsController {

  private final UserSettingsService settingsService;

  public SettingsController(UserSettingsService settingsService) {
    this.settingsService = settingsService;
  }

  @GetMapping
  public ResponseEntity<UserSettingsDTO> getSettings(Authentication authentication) {
    UUID userId = UUID.fromString((String) authentication.getPrincipal());
    UserSettingsDTO settings = settingsService.getSettings(userId);
    return ResponseEntity.ok(settings);
  }

  @PatchMapping
  public ResponseEntity<UserSettingsDTO> updateSettings(
      Authentication authentication, @RequestBody UpdateSettingsRequest request) {
    UUID userId = UUID.fromString((String) authentication.getPrincipal());
    UserSettingsDTO settings = settingsService.updateSettings(userId, request);
    return ResponseEntity.ok(settings);
  }
}
