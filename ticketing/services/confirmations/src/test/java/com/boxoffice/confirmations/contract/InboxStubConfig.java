package com.boxoffice.confirmations.contract;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

/** Stands in for the orders and seats inboxes so the contract run needs no other service. */
@TestConfiguration
class InboxStubConfig {

    private final RestClient.Builder builder = RestClient.builder();

    @Bean
    MockRestServiceServer inboxServer() {
        return MockRestServiceServer.bindTo(builder).ignoreExpectOrder(true).build();
    }

    @Bean
    @Primary
    RestClient stubbedInboxRestClient(MockRestServiceServer inboxServer) {
        return builder.build();
    }
}
