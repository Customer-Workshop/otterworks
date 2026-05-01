package com.otterworks.auth.dto;

import com.otterworks.auth.entity.UserSettings;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@AllArgsConstructor
@NoArgsConstructor
public class UserSettingsDTO {

  private boolean notificationEmail;
  private boolean notificationInApp;
  private boolean notificationDesktop;
  private String theme;
  private String language;

  public static UserSettingsDTO fromEntity(UserSettings entity) {
    UserSettingsDTO dto = new UserSettingsDTO();
    dto.setNotificationEmail(entity.isNotificationEmail());
    dto.setNotificationInApp(entity.isNotificationInApp());
    dto.setNotificationDesktop(entity.isNotificationDesktop());
    dto.setTheme(entity.getTheme());
    dto.setLanguage(entity.getLanguage());
    return dto;
  }
}
