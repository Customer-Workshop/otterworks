package com.boxoffice.confirmations.config;

import java.time.Duration;
import org.springframework.boot.web.client.ClientHttpRequestFactories;
import org.springframework.boot.web.client.ClientHttpRequestFactorySettings;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class ClientConfig {

    @Bean
    RestClient inboxRestClient(ConfirmationsProperties props) {
        ClientHttpRequestFactorySettings settings = ClientHttpRequestFactorySettings.DEFAULTS
                .withConnectTimeout(Duration.ofMillis(props.deliveryTimeoutMs()))
                .withReadTimeout(Duration.ofMillis(props.deliveryTimeoutMs()));
        return RestClient.builder()
                .requestFactory(ClientHttpRequestFactories.get(settings))
                .build();
    }
}
