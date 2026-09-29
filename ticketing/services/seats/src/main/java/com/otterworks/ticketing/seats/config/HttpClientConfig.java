package com.otterworks.ticketing.seats.config;

import java.time.Duration;
import org.springframework.boot.web.client.ClientHttpRequestFactories;
import org.springframework.boot.web.client.ClientHttpRequestFactorySettings;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class HttpClientConfig {

    @Bean
    RestClient ordersRestClient(SeatsProperties props) {
        Duration timeout = Duration.ofMillis(props.orders().timeoutMs());
        var settings = ClientHttpRequestFactorySettings.DEFAULTS.withConnectTimeout(timeout).withReadTimeout(timeout);
        return RestClient.builder()
                .baseUrl(props.orders().baseUrl())
                .requestFactory(ClientHttpRequestFactories.get(settings))
                .build();
    }
}
