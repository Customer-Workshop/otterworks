package com.boxoffice.confirmations.contract;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;

/** A recorded monolith interaction under {@code src/test/resources/contracts/<name>.json}. */
final class ContractFixture {

    private static final ObjectMapper JSON = new ObjectMapper();

    private ContractFixture() {
    }

    static JsonNode load(String name) {
        String path = "/contracts/" + name + ".json";
        try (InputStream in = ContractFixture.class.getResourceAsStream(path)) {
            if (in == null) {
                throw new IllegalArgumentException("missing fixture " + path);
            }
            return JSON.readTree(in);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }
}
