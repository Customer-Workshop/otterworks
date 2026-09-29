package com.boxoffice.confirmations.events;

/** Writes the order-confirmed record to Kafka (or, in tests, remembers it). */
public interface OrderConfirmedPublisher {

    /** Returns the topic the record was written to. Throws {@link DeliveryException} if the broker did not ack. */
    String publish(OrderConfirmedEvent event);
}
