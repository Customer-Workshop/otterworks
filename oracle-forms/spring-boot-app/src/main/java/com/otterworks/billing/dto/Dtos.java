package com.otterworks.billing.dto;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;

/** Request/response DTOs for the billing API (camelCase, per the OpenAPI contract). */
public final class Dtos {
  private Dtos() {}

  public record PlanResponse(
      String planCode,
      String planName,
      BigDecimal monthlyPrice,
      int includedGb,
      int maxSeats,
      BigDecimal maxDiscountPct) {}

  public record CustomerResponse(
      Long customerId, String companyName, String contactEmail, String status, Instant createdAt) {}

  public record CustomerRequest(String companyName, String contactEmail, String status) {}

  public record SubscriptionResponse(
      Long subscriptionId,
      Long customerId,
      String planCode,
      int seats,
      BigDecimal discountPct,
      LocalDate startDate,
      LocalDate endDate,
      String status) {}

  public record SubscriptionRequest(
      String planCode,
      Integer seats,
      BigDecimal discountPct,
      LocalDate startDate,
      LocalDate endDate) {}

  public record ErrorResponse(String field, String message) {}
}
