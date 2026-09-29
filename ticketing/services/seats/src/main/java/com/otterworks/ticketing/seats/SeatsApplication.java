package com.otterworks.ticketing.seats;

import com.otterworks.ticketing.seats.config.SeatsProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(SeatsProperties.class)
public class SeatsApplication {
    public static void main(String[] args) {
        SpringApplication.run(SeatsApplication.class, args);
    }
}
