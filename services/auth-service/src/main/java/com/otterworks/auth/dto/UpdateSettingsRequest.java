package com.otterworks.auth.dto;

import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
public class UpdateSettingsRequest {

  private Boolean notificationEmail;
  private Boolean notificationInApp;
  private Boolean notificationDesktop;
  private String theme;
  private String language;
}
