package com.otterworks.auth.entity;

import jakarta.persistence.*;
import java.util.UUID;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

@Entity
@Table(name = "user_settings")
@Getter
@Setter
@NoArgsConstructor
public class UserSettings {

  @Id
  @Column(name = "user_id")
  private UUID userId;

  @OneToOne(fetch = FetchType.LAZY)
  @MapsId
  @JoinColumn(name = "user_id")
  private User user;

  @Column(name = "notification_email", nullable = false)
  private boolean notificationEmail = true;

  @Column(name = "notification_in_app", nullable = false)
  private boolean notificationInApp = true;

  @Column(name = "notification_desktop", nullable = false)
  private boolean notificationDesktop = false;

  @Column(nullable = false, length = 10)
  private String theme = "system";

  @Column(nullable = false, length = 10)
  private String language = "en";
}
