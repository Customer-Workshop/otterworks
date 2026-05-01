package com.otterworks.auth.dto;

import com.otterworks.auth.entity.UserSettings;
import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
public class UserSettingsDTO {
  private boolean notificationEmail;
  private boolean notificationInApp;
  private boolean notificationDesktop;
  private String theme;
  private String language;

  public static UserSettingsDTO fromEntity(UserSettings entity) {
    return new UserSettingsDTO(
        entity.isNotificationEmail(),
        entity.isNotificationInApp(),
        entity.isNotificationDesktop(),
        entity.getTheme(),
        entity.getLanguage());
  }

  public static UserSettingsDTO defaults() {
    return new UserSettingsDTO(true, true, false, "system", "en");
  }
}
