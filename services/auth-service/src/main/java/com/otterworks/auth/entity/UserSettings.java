package com.otterworks.auth.entity;

import jakarta.persistence.*;
import java.time.Instant;
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

  @Column(nullable = false)
  private boolean notificationEmail = true;

  @Column(nullable = false)
  private boolean notificationInApp = true;

  @Column(nullable = false)
  private boolean notificationDesktop = false;

  @Column(nullable = false, length = 20)
  private String theme = "system";

  @Column(nullable = false, length = 10)
  private String language = "en";

  @Column(nullable = false)
  private Instant updatedAt;

  @PrePersist
  protected void onCreate() {
    updatedAt = Instant.now();
  }

  @PreUpdate
  protected void onUpdate() {
    updatedAt = Instant.now();
  }
}
