package com.otterworks.billing.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;

@Entity
@Table(name = "storage_plans")
public class Plan {
  @Id
  @Column(name = "plan_code")
  private String planCode;

  @Column(name = "plan_name")
  private String planName;

  @Column(name = "monthly_price")
  private BigDecimal monthlyPrice;

  @Column(name = "included_gb")
  private int includedGb;

  @Column(name = "max_seats")
  private int maxSeats;

  @Column(name = "max_discount_pct")
  private BigDecimal maxDiscountPct;

  public String getPlanCode() {
    return planCode;
  }

  public String getPlanName() {
    return planName;
  }

  public BigDecimal getMonthlyPrice() {
    return monthlyPrice;
  }

  public int getIncludedGb() {
    return includedGb;
  }

  public int getMaxSeats() {
    return maxSeats;
  }

  public BigDecimal getMaxDiscountPct() {
    return maxDiscountPct;
  }
}
