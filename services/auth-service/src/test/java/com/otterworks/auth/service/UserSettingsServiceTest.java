package com.otterworks.auth.service;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import com.otterworks.auth.dto.UpdateSettingsRequest;
import com.otterworks.auth.dto.UserSettingsDTO;
import com.otterworks.auth.entity.User;
import com.otterworks.auth.entity.UserSettings;
import com.otterworks.auth.repository.UserRepository;
import com.otterworks.auth.repository.UserSettingsRepository;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class UserSettingsServiceTest {

  @Mock private UserSettingsRepository settingsRepository;
  @Mock private UserRepository userRepository;

  @InjectMocks private UserSettingsService settingsService;

  private UUID userId;
  private User testUser;

  @BeforeEach
  void setUp() {
    userId = UUID.randomUUID();
    testUser = new User();
    testUser.setId(userId);
    testUser.setEmail("test@otterworks.dev");
  }

  @Test
  void getSettings_shouldReturnExistingSettings() {
    UserSettings settings = new UserSettings();
    settings.setTheme("dark");
    settings.setLanguage("de");
    when(settingsRepository.findById(userId)).thenReturn(Optional.of(settings));

    UserSettingsDTO dto = settingsService.getSettings(userId);

    assertThat(dto.getTheme()).isEqualTo("dark");
    assertThat(dto.getLanguage()).isEqualTo("de");
    verify(userRepository, never()).findById(any());
  }

  @Test
  void getSettings_shouldCreateDefaultsWhenMissing() {
    when(settingsRepository.findById(userId)).thenReturn(Optional.empty());
    when(userRepository.findById(userId)).thenReturn(Optional.of(testUser));
    when(settingsRepository.save(any(UserSettings.class))).thenAnswer(inv -> inv.getArgument(0));

    UserSettingsDTO dto = settingsService.getSettings(userId);

    assertThat(dto.isNotificationEmail()).isTrue();
    assertThat(dto.isNotificationInApp()).isTrue();
    assertThat(dto.isNotificationDesktop()).isFalse();
    assertThat(dto.getTheme()).isEqualTo("system");
    assertThat(dto.getLanguage()).isEqualTo("en");
    verify(settingsRepository).save(any(UserSettings.class));
  }

  @Test
  void getSettings_shouldThrowWhenUserMissing() {
    when(settingsRepository.findById(userId)).thenReturn(Optional.empty());
    when(userRepository.findById(userId)).thenReturn(Optional.empty());

    assertThatThrownBy(() -> settingsService.getSettings(userId))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessage("User not found");
  }

  @Test
  void updateSettings_shouldUpdateOnlyProvidedFields() {
    UserSettings settings = new UserSettings();
    when(settingsRepository.findById(userId)).thenReturn(Optional.of(settings));
    when(settingsRepository.save(any(UserSettings.class))).thenAnswer(inv -> inv.getArgument(0));

    UpdateSettingsRequest request = new UpdateSettingsRequest();
    request.setTheme("dark");
    request.setNotificationDesktop(true);

    UserSettingsDTO dto = settingsService.updateSettings(userId, request);

    assertThat(dto.getTheme()).isEqualTo("dark");
    assertThat(dto.isNotificationDesktop()).isTrue();
    // untouched fields keep their defaults
    assertThat(dto.isNotificationEmail()).isTrue();
    assertThat(dto.isNotificationInApp()).isTrue();
    assertThat(dto.getLanguage()).isEqualTo("en");
  }

  @Test
  void updateSettings_shouldAllowDisablingNotifications() {
    UserSettings settings = new UserSettings();
    when(settingsRepository.findById(userId)).thenReturn(Optional.of(settings));
    when(settingsRepository.save(any(UserSettings.class))).thenAnswer(inv -> inv.getArgument(0));

    UpdateSettingsRequest request = new UpdateSettingsRequest();
    request.setNotificationEmail(false);
    request.setNotificationInApp(false);

    UserSettingsDTO dto = settingsService.updateSettings(userId, request);

    assertThat(dto.isNotificationEmail()).isFalse();
    assertThat(dto.isNotificationInApp()).isFalse();
  }

  @Test
  void updateSettings_shouldCreateDefaultsWhenMissingThenApplyUpdates() {
    when(settingsRepository.findById(userId)).thenReturn(Optional.empty());
    when(userRepository.findById(userId)).thenReturn(Optional.of(testUser));
    when(settingsRepository.save(any(UserSettings.class))).thenAnswer(inv -> inv.getArgument(0));

    UpdateSettingsRequest request = new UpdateSettingsRequest();
    request.setLanguage("fr");

    UserSettingsDTO dto = settingsService.updateSettings(userId, request);

    assertThat(dto.getLanguage()).isEqualTo("fr");
    verify(settingsRepository, times(2)).save(any(UserSettings.class));
  }
}
