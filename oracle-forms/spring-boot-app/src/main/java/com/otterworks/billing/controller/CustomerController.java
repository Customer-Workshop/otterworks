package com.otterworks.billing.controller;

import com.otterworks.billing.dto.Dtos.CustomerRequest;
import com.otterworks.billing.dto.Dtos.CustomerResponse;
import com.otterworks.billing.model.Customer;
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
@RequestMapping("/api/customers")
public class CustomerController {
  private final BillingService service;

  public CustomerController(BillingService service) {
    this.service = service;
  }

  @GetMapping
  public List<CustomerResponse> list() {
    return service.listCustomers().stream().map(CustomerController::toDto).toList();
  }

  @GetMapping("/{customerId}")
  public CustomerResponse get(@PathVariable Long customerId) {
    return toDto(service.getCustomer(customerId));
  }

  @PostMapping
  @ResponseStatus(HttpStatus.CREATED)
  public CustomerResponse create(@RequestBody CustomerRequest req) {
    return toDto(service.createCustomer(req.companyName(), req.contactEmail(), req.status()));
  }

  static CustomerResponse toDto(Customer c) {
    return new CustomerResponse(
        c.getCustomerId(),
        c.getCompanyName(),
        c.getContactEmail(),
        c.getStatus(),
        c.getCreatedAt());
  }
}
