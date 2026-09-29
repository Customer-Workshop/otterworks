package com.boxoffice.common;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class JsonTest {

    @Test
    void writesNestedStructures() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("ref", "BO-1");
        m.put("tickets", 2);
        m.put("ok", true);
        m.put("seats", List.of("A-1", "A-2"));
        assertEquals("{\"ref\":\"BO-1\",\"tickets\":2,\"ok\":true,\"seats\":[\"A-1\",\"A-2\"]}", Json.write(m));
    }
}
