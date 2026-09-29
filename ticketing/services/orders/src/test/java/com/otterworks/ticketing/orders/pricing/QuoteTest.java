package com.otterworks.ticketing.orders.pricing;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;

class QuoteTest {

    @Test
    void feeRowsMatchTheMonolithIncludingFreeDeliveryOmission() {
        Quote mobile = new Quote(1, List.of(), 37800, 4536, 500, 0, 5036, 42836, null, null, 1L);
        assertThat(mobile.fees()).extracting(Quote.Fee::feeType).containsExactly("SERVICE", "FACILITY");
        Quote print = new Quote(1, List.of(), 37800, 4536, 500, 150, 5186, 42986, null, null, 2L);
        assertThat(print.fees()).extracting(Quote.Fee::feeType).containsExactly("SERVICE", "FACILITY", "DELIVERY");
        assertThat(print.fees().stream().mapToLong(Quote.Fee::amountCents).sum()).isEqualTo(print.feesCents());
    }
}
