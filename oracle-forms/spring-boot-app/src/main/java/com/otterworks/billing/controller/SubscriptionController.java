package com.otterworks.billing.controller;

import com.otterworks.billing.dto.Dtos.SubscriptionRequest;
import com.otterworks.billing.dto.Dtos.SubscriptionResponse;
import com.otterworks.billing.model.Subscription;
import com.otterworks.billing.service.BillingService;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/customers/{customerId}/subscriptions")
public class SubscriptionController {
  private final BillingService service;

  public SubscriptionController(BillingService service) {
    this.service = service;
  }

  @GetMapping
  public List<SubscriptionResponse> list(@PathVariable Long customerId) {
    return service.listSubscriptions(customerId).stream()
        .map(SubscriptionController::toDto)
        .toList();
  }

  @PostMapping
  @ResponseStatus(HttpStatus.CREATED)
  public SubscriptionResponse create(
      @PathVariable Long customerId, @RequestBody SubscriptionRequest req) {
    return toDto(
        service.createSubscription(
            customerId,
            req.planCode(),
            req.seats(),
            req.discountPct(),
            req.startDate(),
            req.endDate()));
  }

  static SubscriptionResponse toDto(Subscription s) {
    return new SubscriptionResponse(
        s.getSubscriptionId(),
        s.getCustomerId(),
        s.getPlanCode(),
        s.getSeats(),
        s.getDiscountPct(),
        s.getStartDate(),
        s.getEndDate(),
        s.getStatus());
  }
}
