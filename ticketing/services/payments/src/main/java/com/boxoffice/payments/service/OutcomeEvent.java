package com.boxoffice.payments.service;

import com.boxoffice.payments.events.PaymentCaptured;
import com.boxoffice.payments.events.PaymentFailed;

/** Exactly one of captured / failed is set: the event the consumer must deliver before committing the offset. */
public record OutcomeEvent(PaymentCaptured captured, PaymentFailed failed, boolean duplicate) {

    public static OutcomeEvent of(PaymentCaptured captured, boolean duplicate) {
        return new OutcomeEvent(captured, null, duplicate);
    }

    public static OutcomeEvent of(PaymentFailed failed, boolean duplicate) {
        return new OutcomeEvent(null, failed, duplicate);
    }

    public String orderRef() {
        return captured != null ? captured.orderRef() : failed.orderRef();
    }
}
