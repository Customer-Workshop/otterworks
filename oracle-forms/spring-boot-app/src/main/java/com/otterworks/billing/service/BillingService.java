package com.otterworks.billing.service;

import com.otterworks.billing.exception.NotImplementedException;
import com.otterworks.billing.model.Customer;
import com.otterworks.billing.model.Plan;
import com.otterworks.billing.model.Subscription;
import com.otterworks.billing.repository.CustomerRepository;
import com.otterworks.billing.repository.PlanRepository;
import com.otterworks.billing.repository.SubscriptionRepository;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import org.springframework.stereotype.Service;

/**
 * SCAFFOLD ONLY — the business logic is intentionally unimplemented.
 *
 * <p>The modernization task is to implement these methods so the REST API reproduces the behavior
 * of the legacy Oracle Forms module BILLING.fmb. The source of truth is:
 *
 * <ul>
 *   <li>oracle-forms/contracts/openapi.yaml — the REST contract
 *   <li>oracle-forms/legacy/BILLING.fmb.xml — the Forms blocks/items/triggers
 *   <li>oracle-forms/legacy/triggers/*.plsql — the extracted WHEN-VALIDATE-* trigger bodies
 * </ul>
 *
 * <p>Each unimplemented method currently returns HTTP 501. Implement the rules, then prove parity
 * with {@code make forms-verify}.
 */
@Service
public class BillingService {
  private final PlanRepository plans;
  private final CustomerRepository customers;
  private final SubscriptionRepository subscriptions;

  public BillingService(
      PlanRepository plans, CustomerRepository customers, SubscriptionRepository subscriptions) {
    this.plans = plans;
    this.customers = customers;
    this.subscriptions = subscriptions;
  }

  public List<Plan> listPlans() {
    throw new NotImplementedException();
  }

  public Plan getPlan(String planCode) {
    throw new NotImplementedException();
  }

  public List<Customer> listCustomers() {
    throw new NotImplementedException();
  }

  public Customer getCustomer(Long id) {
    throw new NotImplementedException();
  }

  public Customer createCustomer(String companyName, String contactEmail, String status) {
    // TODO: reproduce CUSTOMERS.CONTACT_EMAIL WHEN-VALIDATE-ITEM + STATUS LOV
    throw new NotImplementedException();
  }

  public List<Subscription> listSubscriptions(Long customerId) {
    throw new NotImplementedException();
  }

  public Subscription createSubscription(
      Long customerId,
      String planCode,
      Integer seats,
      BigDecimal discountPct,
      LocalDate startDate,
      LocalDate endDate) {
    // TODO: reproduce the SUBSCRIPTIONS triggers (SEATS, DISCOUNT_PCT, WHEN-VALIDATE-RECORD,
    // PRE-INSERT). See oracle-forms/legacy/triggers/.
    throw new NotImplementedException();
  }
}
