package com.otterworks.ticketing.orders.support;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.test.web.client.MockServerRestClientCustomizer;
import org.springframework.context.annotation.Bean;

/** Binds a MockRestServiceServer to the seats RestClient so tests script the seats service. */
@TestConfiguration
public class SeatsStubConfig {

    @Bean
    MockServerRestClientCustomizer mockServerRestClientCustomizer() {
        return new MockServerRestClientCustomizer();
    }
}
