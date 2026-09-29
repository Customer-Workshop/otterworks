package com.boxoffice.payments.domain;

/** The sibling services with an HTTP inbox; the base URL comes from payments.inbox.* at relay time. */
public enum DeliveryTarget {
    CONFIRMATIONS, ORDERS, SEATS
}
