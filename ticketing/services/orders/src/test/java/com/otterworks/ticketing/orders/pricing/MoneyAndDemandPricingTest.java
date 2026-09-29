package com.otterworks.ticketing.orders.pricing;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class MoneyAndDemandPricingTest {

    @Test
    void percentOfRoundsHalfUpLikeTheMonolith() {
        assertThat(Money.percentOf(37800, 1200)).isEqualTo(4536);
        assertThat(Money.percentOf(32130, 1200)).isEqualTo(3856); // 3855.6 -> 3856
        assertThat(Money.percentOf(18900, 10500)).isEqualTo(19845);
        assertThat(Money.percentOf(5, 5000)).isEqualTo(3);         // 2.5 -> 3
        assertThat(Money.percentOf(0, 1200)).isZero();
    }

    @ParameterizedTest(name = "{0}/{1} not available -> +{2}bp")
    @CsvSource({
            "0, 4000, 0",
            "2, 4000, 0",
            "399, 4000, 0",
            "400, 4000, 500",
            "799, 4000, 500",
            "800, 4000, 1000",
            "3200, 4000, 4000",
            "4000, 4000, 4000",
            "1, 1, 4000",
            "0, 0, 0"
    })
    void upliftIsFivePercentPerTenPercentSoldCappedAtForty(long notAvailable, long total, int expectedBp) {
        assertThat(DemandPricing.upliftBp(notAvailable, total)).isEqualTo(expectedBp);
    }

    @Test
    void linePriceAppliesDemandFactorAndUplift() {
        assertThat(DemandPricing.linePrice(18900, 10000, 0)).isEqualTo(18900);
        assertThat(DemandPricing.linePrice(18900, 10000, 500)).isEqualTo(19845);
        assertThat(DemandPricing.linePrice(18900, 10000, 4000)).isEqualTo(26460);
        assertThat(DemandPricing.linePrice(6900, 11000, 0)).isEqualTo(7590);
    }
}
