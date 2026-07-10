package com.otterworks.billing.controller;

import com.otterworks.billing.dto.Dtos.PlanResponse;
import com.otterworks.billing.model.Plan;
import com.otterworks.billing.service.BillingService;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/plans")
public class PlanController {
  private final BillingService service;

  public PlanController(BillingService service) {
    this.service = service;
  }

  @GetMapping
  public List<PlanResponse> list() {
    return service.listPlans().stream().map(PlanController::toDto).toList();
  }

  @GetMapping("/{planCode}")
  public PlanResponse get(@PathVariable String planCode) {
    return toDto(service.getPlan(planCode));
  }

  static PlanResponse toDto(Plan p) {
    return new PlanResponse(
        p.getPlanCode(),
        p.getPlanName(),
        p.getMonthlyPrice(),
        p.getIncludedGb(),
        p.getMaxSeats(),
        p.getMaxDiscountPct());
  }
}
