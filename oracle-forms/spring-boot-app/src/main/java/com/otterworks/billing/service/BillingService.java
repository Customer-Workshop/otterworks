package com.otterworks.billing.service;

import com.otterworks.billing.exception.NotFoundException;
import com.otterworks.billing.exception.ValidationException;
import com.otterworks.billing.model.Customer;
import com.otterworks.billing.model.Plan;
import com.otterworks.billing.model.Subscription;
import com.otterworks.billing.repository.CustomerRepository;
import com.otterworks.billing.repository.PlanRepository;
import com.otterworks.billing.repository.SubscriptionRepository;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import org.springframework.stereotype.Service;

/**
 * Business logic reproducing the BILLING.fmb Forms triggers. Each validation below cites the Forms
 * trigger it reproduces; see oracle-forms/legacy/triggers/.
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
    return plans.findAll();
  }

  public Plan getPlan(String planCode) {
    return plans
        .findById(planCode)
        .orElseThrow(() -> new NotFoundException("Unknown plan " + planCode));
  }

  public List<Customer> listCustomers() {
    return customers.findAll();
  }

  public Customer getCustomer(Long id) {
    return customers
        .findById(id)
        .orElseThrow(() -> new NotFoundException("Unknown customer " + id));
  }

  public Customer createCustomer(String companyName, String contactEmail, String status) {
    // CUSTOMERS.COMPANY_NAME: Required, Maximum_Length 100
    if (companyName == null || companyName.isBlank()) {
      throw new ValidationException("companyName", "Company name is required");
    }
    if (companyName.length() > 100) {
      throw new ValidationException("companyName", "Company name exceeds maximum length");
    }
    // CUSTOMERS.CONTACT_EMAIL WHEN-VALIDATE-ITEM: required, email-shaped, maxlen 120
    if (contactEmail == null || !isValidEmail(contactEmail) || contactEmail.length() > 120) {
      throw new ValidationException("contactEmail", "Contact email must be a valid email address");
    }
    // CUSTOMERS.STATUS LOV STATUS_LOV: ACTIVE|SUSPENDED|CLOSED, default ACTIVE
    String resolved = (status == null || status.isBlank()) ? "ACTIVE" : status;
    if (!List.of("ACTIVE", "SUSPENDED", "CLOSED").contains(resolved)) {
      throw new ValidationException("status", "Status must be ACTIVE, SUSPENDED, or CLOSED");
    }
    Customer c = new Customer();
    c.setCompanyName(companyName);
    c.setContactEmail(contactEmail);
    c.setStatus(resolved);
    c.setCreatedAt(Instant.now());
    return customers.save(c);
  }

  public List<Subscription> listSubscriptions(Long customerId) {
    getCustomer(customerId);
    return subscriptions.findByCustomerId(customerId);
  }

  public Subscription createSubscription(
      Long customerId,
      String planCode,
      Integer seatsIn,
      BigDecimal discountIn,
      java.time.LocalDate startDate,
      java.time.LocalDate endDate) {
    Customer customer = getCustomer(customerId);

    // SUBSCRIPTIONS.PLAN_CODE LOV PLAN_LOV: must exist in STORAGE_PLANS
    if (planCode == null || planCode.isBlank()) {
      throw new ValidationException("planCode", "Plan code is required");
    }
    Plan plan =
        plans
            .findById(planCode)
            .orElseThrow(() -> new ValidationException("planCode", "Unknown plan code"));

    // SUBSCRIPTIONS.START_DATE: Required
    if (startDate == null) {
      throw new ValidationException("startDate", "Start date is required");
    }

    int seats = seatsIn == null ? 1 : seatsIn;
    BigDecimal discount = discountIn == null ? BigDecimal.ZERO : discountIn;

    // SUBSCRIPTIONS.SEATS WHEN-VALIDATE-ITEM: 1 <= seats <= plan.maxSeats (cross-field)
    if (seats < 1) {
      throw new ValidationException("seats", "Seats must be at least 1");
    }
    if (seats > plan.getMaxSeats()) {
      throw new ValidationException("seats", "Seats exceed plan maximum");
    }

    // SUBSCRIPTIONS.DISCOUNT_PCT WHEN-VALIDATE-ITEM: 0 <= discount <= plan.maxDiscountPct
    // (cross-field: non-enterprise plans carry maxDiscountPct = 0)
    if (discount.compareTo(BigDecimal.ZERO) < 0) {
      throw new ValidationException("discountPct", "Discount must not be negative");
    }
    if (discount.compareTo(plan.getMaxDiscountPct()) > 0) {
      throw new ValidationException("discountPct", "Discount exceeds plan maximum");
    }

    // SUBSCRIPTIONS WHEN-VALIDATE-RECORD: endDate must be after startDate when present
    if (endDate != null && !endDate.isAfter(startDate)) {
      throw new ValidationException("endDate", "End date must be after start date");
    }

    // SUBSCRIPTIONS PRE-INSERT: customer must not be CLOSED
    if ("CLOSED".equals(customer.getStatus())) {
      throw new ValidationException("customerId", "Cannot add subscription for a closed customer");
    }

    Subscription s = new Subscription();
    s.setCustomerId(customerId);
    s.setPlanCode(planCode);
    s.setSeats(seats);
    s.setDiscountPct(discount);
    s.setStartDate(startDate);
    s.setEndDate(endDate);
    s.setStatus("ACTIVE");
    return subscriptions.save(s);
  }

  private static boolean isValidEmail(String email) {
    int at = email.indexOf('@');
    return at > 0 && email.indexOf('.', at) > at;
  }
}
