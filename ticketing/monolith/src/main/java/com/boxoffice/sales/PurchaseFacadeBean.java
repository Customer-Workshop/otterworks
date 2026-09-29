package com.boxoffice.sales;

import com.boxoffice.common.BoxOfficeException;
import com.boxoffice.customer.CustomerAccountBean;
import com.boxoffice.fulfillment.ConfirmationBean;
import com.boxoffice.inventory.SeatHoldBean;
import com.boxoffice.payment.PaymentBean;
import com.boxoffice.payment.PaymentGatewayClient;
import com.boxoffice.pricing.PricingBean;
import jakarta.ejb.EJB;
import jakarta.ejb.Stateless;
import jakarta.ejb.TransactionAttribute;
import jakarta.ejb.TransactionAttributeType;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * The purchase path. One container transaction spans customer lookup, seat hold, pricing,
 * order placement, the synchronous gateway call and ticket issue.
 */
@Stateless
public class PurchaseFacadeBean {

    @EJB
    private CustomerAccountBean customers;
    @EJB
    private SeatHoldBean holds;
    @EJB
    private PricingBean pricing;
    @EJB
    private OrderBean orders;
    @EJB
    private PaymentBean payments;
    @EJB
    private ConfirmationBean confirmations;

    @TransactionAttribute(TransactionAttributeType.REQUIRED)
    public Map<String, Object> purchase(long performanceId, String email, int quantity, String sectionCode,
                                        String promoCode, String deliveryCode, String cardLast4, String channel) {
        long customerId = customers.findOrCreate(email, null);
        long holdId = holds.hold(performanceId, customerId, quantity, sectionCode);
        return completeHold(customerId, holdId, promoCode, deliveryCode, cardLast4, channel);
    }

    @TransactionAttribute(TransactionAttributeType.REQUIRED)
    public Map<String, Object> checkout(long customerId, long holdId, String promoCode, String deliveryCode,
                                        String cardLast4) {
        if (!holds.isActive(holdId)) {
            throw new BoxOfficeException("HOLD_EXPIRED", "hold expired before checkout");
        }
        return completeHold(customerId, holdId, promoCode, deliveryCode, cardLast4, "WEB");
    }

    private Map<String, Object> completeHold(long customerId, long holdId, String promoCode, String deliveryCode,
                                             String cardLast4, String channel) {
        PricingBean.Quote q = pricing.quote(holdId, promoCode, deliveryCode);
        long orderId = orders.place(customerId, holdId, q, channel);
        PaymentGatewayClient.Outcome outcome = payments.charge(orderId, cardLast4);
        int tickets = 0;
        if (outcome == PaymentGatewayClient.Outcome.APPROVED) {
            tickets = confirmations.confirm(orderId);
        }
        Map<String, Object> order = orders.byId(orderId);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("orderRef", order.get("order_ref"));
        out.put("status", order.get("status"));
        out.put("totalCents", order.get("total_cents"));
        out.put("tickets", tickets);
        out.put("paymentOutcome", outcome.name());
        return out;
    }
}
