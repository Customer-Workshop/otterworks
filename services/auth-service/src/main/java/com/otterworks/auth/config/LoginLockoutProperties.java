package com.otterworks.auth.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "auth.lockout")
public class LoginLockoutProperties {

  /** Failed attempts within the window before the account is locked. */
  private int maxAttempts = 5;

  /** Failures older than this are forgotten. */
  private Duration window = Duration.ofMinutes(15);

  /** Lockout applied when the threshold is first reached. */
  private Duration baseDuration = Duration.ofMinutes(1);

  /** Upper bound for the progressive lockout. */
  private Duration maxDuration = Duration.ofHours(1);

  public int getMaxAttempts() {
    return maxAttempts;
  }

  public void setMaxAttempts(int maxAttempts) {
    this.maxAttempts = maxAttempts;
  }

  public Duration getWindow() {
    return window;
  }

  public void setWindow(Duration window) {
    this.window = window;
  }

  public Duration getBaseDuration() {
    return baseDuration;
  }

  public void setBaseDuration(Duration baseDuration) {
    this.baseDuration = baseDuration;
  }

  public Duration getMaxDuration() {
    return maxDuration;
  }

  public void setMaxDuration(Duration maxDuration) {
    this.maxDuration = maxDuration;
  }
}
