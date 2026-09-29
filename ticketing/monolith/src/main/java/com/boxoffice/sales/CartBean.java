package com.boxoffice.sales;

import com.boxoffice.inventory.SeatHoldBean;
import com.boxoffice.pricing.PricingBean;
import jakarta.ejb.EJB;
import jakarta.ejb.Remove;
import jakarta.ejb.Stateful;
import jakarta.ejb.StatefulTimeout;
import java.io.Serializable;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

/** Conversational state for the web checkout: one hold, a promo and a delivery choice. */
@Stateful
@StatefulTimeout(value = 30, unit = TimeUnit.MINUTES)
public class CartBean implements Serializable {

    private static final long serialVersionUID = 1L;

    @EJB
    private SeatHoldBean holds;

    @EJB
    private PricingBean pricing;

    private Long holdId;
    private Long customerId;
    private String promoCode;
    private String deliveryCode = "MOBILE";

    public void holdSeats(long performanceId, Long customer, int quantity, String sectionCode) {
        if (holdId != null && holds.isActive(holdId)) {
            holds.release(holdId, "RELEASED");
        }
        this.customerId = customer;
        this.holdId = holds.hold(performanceId, customer, quantity, sectionCode);
    }

    public PricingBean.Quote quote() {
        return holdId == null ? null : pricing.quote(holdId, promoCode, deliveryCode);
    }

    public List<Map<String, Object>> seats() {
        return holdId == null ? List.of() : holds.items(holdId);
    }

    public Map<String, Object> holdRow() {
        return holdId == null ? null : holds.hold(holdId);
    }

    public boolean holdActive() {
        return holdId != null && holds.isActive(holdId);
    }

    public Long getHoldId() {
        return holdId;
    }

    public Long getCustomerId() {
        return customerId;
    }

    public void setCustomerId(Long customerId) {
        this.customerId = customerId;
    }

    public void setPromoCode(String promoCode) {
        this.promoCode = promoCode;
    }

    public String getPromoCode() {
        return promoCode;
    }

    public void setDeliveryCode(String deliveryCode) {
        this.deliveryCode = deliveryCode;
    }

    public String getDeliveryCode() {
        return deliveryCode;
    }

    @Remove
    public void clear() {
        holdId = null;
    }
}
