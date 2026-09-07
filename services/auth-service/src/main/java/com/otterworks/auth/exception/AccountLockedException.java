package com.otterworks.auth.exception;

public class AccountLockedException extends RuntimeException {

  private final long retryAfterSeconds;

  public AccountLockedException(long retryAfterSeconds) {
    super("Account temporarily locked due to too many failed login attempts");
    this.retryAfterSeconds = retryAfterSeconds;
  }

  public long getRetryAfterSeconds() {
    return retryAfterSeconds;
  }
}
