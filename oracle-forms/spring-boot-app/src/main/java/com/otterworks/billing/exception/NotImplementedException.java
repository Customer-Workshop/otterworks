package com.otterworks.billing.exception;

/** Marker for scaffold endpoints that have not been implemented yet (HTTP 501). */
public class NotImplementedException extends RuntimeException {
  public NotImplementedException() {
    super("Not implemented");
  }
}
