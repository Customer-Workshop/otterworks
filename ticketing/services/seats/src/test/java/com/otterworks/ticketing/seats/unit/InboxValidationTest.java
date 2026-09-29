package com.otterworks.ticketing.seats.unit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.otterworks.ticketing.seats.domain.HoldService;
import com.otterworks.ticketing.seats.domain.SeatsException;
import com.otterworks.ticketing.seats.events.InboxService;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

class InboxValidationTest {

    private final JdbcTemplate jdbc = mock(JdbcTemplate.class);
    private final HoldService holds = mock(HoldService.class);
    private final InboxService inbox = new InboxService(jdbc, holds, new SimpleMeterRegistry());
    private final ObjectMapper json = new ObjectMapper();

    @Test
    void paymentFailedRequiresOrderRefAndHoldRef() throws Exception {
        assertThatThrownBy(() -> inbox.paymentFailed(json.readTree("{\"holdRef\":\"H-A\"}")))
                .isInstanceOf(SeatsException.class)
                .satisfies(e -> assertThat(((SeatsException) e).code()).isEqualTo("BAD_REQUEST"));
        assertThatThrownBy(() -> inbox.paymentFailed(json.readTree("{\"orderRef\":\"BO-A\",\"holdRef\":null}")))
                .isInstanceOf(SeatsException.class);
        verifyNoInteractions(holds);
    }

    @Test
    void orderConfirmedRequiresOrderRefAndHoldRef() throws Exception {
        assertThatThrownBy(() -> inbox.orderConfirmed(json.readTree("{\"orderRef\":\"BO-A\"}")))
                .isInstanceOf(SeatsException.class);
        verifyNoInteractions(holds);
    }
}
