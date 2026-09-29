package com.otterworks.ticketing.orders.config;

import org.springframework.boot.web.client.RestClientCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration
public class ClientConfig {

    @Bean
    @Order(0)
    RestClientCustomizer seatsTimeouts(OrdersProperties props) {
        return builder -> {
            SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
            factory.setConnectTimeout(props.seats().connectTimeout());
            factory.setReadTimeout(props.seats().readTimeout());
            builder.requestFactory(factory);
        };
    }

    @Bean
    RestClient seatsRestClient(RestClient.Builder builder, OrdersProperties props) {
        return builder.baseUrl(props.seats().baseUrl()).build();
    }
}
