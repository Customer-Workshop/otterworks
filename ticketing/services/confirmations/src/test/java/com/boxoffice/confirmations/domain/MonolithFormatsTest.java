package com.boxoffice.confirmations.domain;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class MonolithFormatsTest {

    @ParameterizedTest
    @CsvSource(quoteCharacter = '`', value = {"0,$0.00", "5,$0.05", "42836,$428.36", "`128508`,`$1,285.08`", "`100000000`,`$1,000,000.00`"})
    void moneyMatchesMonolithMoneyFormat(long cents, String expected) {
        // com.boxoffice.common.Money.format: String.format("$%d.%02d", cents/100, cents%100)
        assertThat(MonolithFormats.money(cents)).isEqualTo(expected);
    }

    @Test
    void startsAtKeepsMonolithTimestampRendering() {
        assertThat(MonolithFormats.startsAt("2026-10-20 20:00:00.0")).isEqualTo("2026-10-20 20:00:00.0");
    }

    @Test
    void startsAtNormalisesIsoLocalAndOffsetForms() {
        assertThat(MonolithFormats.startsAt("2026-10-20T20:00:00")).isEqualTo("2026-10-20 20:00:00.0");
        assertThat(MonolithFormats.startsAt("2026-10-20T20:00:00Z")).isEqualTo("2026-10-20 20:00:00.0");
        assertThat(MonolithFormats.startsAt("2026-10-20T22:00:00+02:00")).isEqualTo("2026-10-20 20:00:00.0");
    }

    @Test
    void startsAtFallsBackToRawAndDashWhenMissing() {
        assertThat(MonolithFormats.startsAt("tonight")).isEqualTo("tonight");
        assertThat(MonolithFormats.startsAt(null)).isEqualTo("-");
    }

    @Test
    void subjectAndBodyMatchConfirmationBean() {
        assertThat(MonolithFormats.subject("Hollow Pines Ensemble: Winter Songs"))
                .isEqualTo("Your tickets for Hollow Pines Ensemble: Winter Songs");
        assertThat(MonolithFormats.body("BO-BZYMKYKBSS", 2, "Hollow Pines Ensemble: Winter Songs", "Ossery Hall",
                "2026-10-20 20:00:00.0", 42836))
                .isEqualTo("Order BO-BZYMKYKBSS: 2 ticket(s) for Hollow Pines Ensemble: Winter Songs at Ossery Hall on 2026-10-20 20:00:00.0. Total $428.36.");
    }

    @Test
    void barcodeIsDeterministicPerTicketAndSeat() {
        String a = MonolithFormats.barcode("TK-AAAAAAAAAA", "BO-X", 120006);
        assertThat(a).isEqualTo(MonolithFormats.barcode("TK-AAAAAAAAAA", "BO-X", 120006)).endsWith("-120006");
        assertThat(a).isNotEqualTo(MonolithFormats.barcode("TK-BBBBBBBBBB", "BO-X", 120006));
    }
}
