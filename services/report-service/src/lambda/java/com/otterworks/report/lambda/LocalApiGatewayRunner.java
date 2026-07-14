package com.otterworks.report.lambda;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Executors;

/**
 * Local, faithful stand-in for API Gateway that fronts the report-service
 * {@link StreamLambdaHandler}. It accepts real HTTP, translates each request
 * into the exact API Gateway AWS_PROXY event JSON, invokes the SAME
 * {@code StreamLambdaHandler.handleRequest(InputStream, OutputStream, Context)}
 * the deployed Lambda uses, and translates the proxy response back to HTTP.
 *
 * <p>Purpose: prove the Lambda + API Gateway code path preserves the
 * report-service HTTP contract when real AWS provisioning is not reachable from
 * the environment. The OtterWorks API gateway is pointed at this process via
 * {@code REPORT_SERVICE_URL}, and the contract/flow suite runs through it
 * unchanged. This runner is NOT part of the deployed artifact's request path.
 */
public final class LocalApiGatewayRunner {

    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final StreamLambdaHandler HANDLER = new StreamLambdaHandler();
    private static final SimpleLambdaContext CONTEXT = new SimpleLambdaContext();

    private LocalApiGatewayRunner() {
    }

    public static void main(String[] args) throws IOException {
        int port = Integer.parseInt(System.getenv().getOrDefault("LOCAL_LAMBDA_PORT", "8091"));
        HttpServer server = HttpServer.create(new InetSocketAddress("0.0.0.0", port), 0);
        server.createContext("/", LocalApiGatewayRunner::handle);
        server.setExecutor(Executors.newFixedThreadPool(16));
        server.start();
        System.out.println("[local-apigw] report-service Lambda handler listening on :" + port);
    }

    private static void handle(HttpExchange exchange) {
        try {
            byte[] responseBytes;
            int status;
            String contentType = "application/json";
            try {
                ObjectNode event = buildProxyEvent(exchange);
                byte[] eventBytes = MAPPER.writeValueAsBytes(event);

                ByteArrayOutputStream out = new ByteArrayOutputStream();
                try (InputStream in = new ByteArrayInputStream(eventBytes)) {
                    HANDLER.handleRequest(in, out, CONTEXT);
                }

                JsonNode response = MAPPER.readTree(out.toByteArray());
                status = response.path("statusCode").asInt(502);

                String body = response.path("body").asText("");
                boolean base64 = response.path("isBase64Encoded").asBoolean(false);
                responseBytes = base64
                        ? Base64.getDecoder().decode(body)
                        : body.getBytes(StandardCharsets.UTF_8);

                applyResponseHeaders(exchange, response);
                JsonNode ctHeader = findHeader(response, "content-type");
                if (ctHeader != null) {
                    contentType = ctHeader.asText();
                }
            } catch (Exception e) {
                status = 502;
                responseBytes = ("{\"error\":\"local lambda invocation failed\",\"detail\":\""
                        + String.valueOf(e.getMessage()).replace('"', '\'') + "\"}")
                        .getBytes(StandardCharsets.UTF_8);
            }

            if (exchange.getResponseHeaders().get("Content-Type") == null) {
                exchange.getResponseHeaders().set("Content-Type", contentType);
            }
            // 204/304 must not carry a body length header per HTTP semantics.
            if (status == 204 || status == 304) {
                exchange.sendResponseHeaders(status, -1);
            } else {
                exchange.sendResponseHeaders(status, responseBytes.length == 0 ? -1 : responseBytes.length);
                if (responseBytes.length > 0) {
                    try (OutputStream os = exchange.getResponseBody()) {
                        os.write(responseBytes);
                    }
                }
            }
        } catch (IOException io) {
            // Nothing more we can do; connection likely closed.
        } finally {
            exchange.close();
        }
    }

    private static ObjectNode buildProxyEvent(HttpExchange exchange) throws IOException {
        String method = exchange.getRequestMethod();
        String path = exchange.getRequestURI().getPath();
        String rawQuery = exchange.getRequestURI().getRawQuery();

        ObjectNode event = MAPPER.createObjectNode();
        event.put("httpMethod", method);
        event.put("path", path);
        event.put("resource", path);
        event.put("isBase64Encoded", false);

        // Headers (single + multi value).
        ObjectNode headers = event.putObject("headers");
        ObjectNode multiHeaders = event.putObject("multiValueHeaders");
        for (Map.Entry<String, List<String>> h : exchange.getRequestHeaders().entrySet()) {
            if (h.getKey() == null || h.getValue().isEmpty()) {
                continue;
            }
            headers.put(h.getKey(), h.getValue().get(h.getValue().size() - 1));
            ArrayNode arr = multiHeaders.putArray(h.getKey());
            for (String v : h.getValue()) {
                arr.add(v);
            }
        }

        // Query string (single + multi value).
        if (rawQuery != null && !rawQuery.isEmpty()) {
            ObjectNode qs = event.putObject("queryStringParameters");
            ObjectNode multiQs = event.putObject("multiValueQueryStringParameters");
            for (String pair : rawQuery.split("&")) {
                int eq = pair.indexOf('=');
                String k = eq >= 0 ? pair.substring(0, eq) : pair;
                String v = eq >= 0 ? pair.substring(eq + 1) : "";
                k = urlDecode(k);
                v = urlDecode(v);
                qs.put(k, v);
                if (!multiQs.has(k)) {
                    multiQs.putArray(k);
                }
                ((ArrayNode) multiQs.get(k)).add(v);
            }
        } else {
            event.putNull("queryStringParameters");
            event.putNull("multiValueQueryStringParameters");
        }

        // Body.
        byte[] body = readAll(exchange.getRequestBody());
        if (body.length > 0) {
            event.put("body", new String(body, StandardCharsets.UTF_8));
        } else {
            event.putNull("body");
        }

        // Minimal request context expected by the proxy model.
        ObjectNode rc = event.putObject("requestContext");
        rc.put("requestId", CONTEXT.getAwsRequestId());
        rc.put("stage", "local");
        rc.put("path", path);
        rc.put("httpMethod", method);
        rc.putObject("identity");
        return event;
    }

    private static void applyResponseHeaders(HttpExchange exchange, JsonNode response) {
        JsonNode headers = response.get("headers");
        if (headers != null && headers.isObject()) {
            Iterator<Map.Entry<String, JsonNode>> it = headers.fields();
            while (it.hasNext()) {
                Map.Entry<String, JsonNode> e = it.next();
                if (e.getValue() != null && !e.getValue().isNull()) {
                    exchange.getResponseHeaders().set(e.getKey(), e.getValue().asText());
                }
            }
        }
        JsonNode multi = response.get("multiValueHeaders");
        if (multi != null && multi.isObject()) {
            Iterator<Map.Entry<String, JsonNode>> it = multi.fields();
            while (it.hasNext()) {
                Map.Entry<String, JsonNode> e = it.next();
                if (e.getValue() != null && e.getValue().isArray()) {
                    for (JsonNode v : e.getValue()) {
                        exchange.getResponseHeaders().add(e.getKey(), v.asText());
                    }
                }
            }
        }
    }

    private static JsonNode findHeader(JsonNode response, String name) {
        JsonNode headers = response.get("headers");
        if (headers != null && headers.isObject()) {
            Iterator<Map.Entry<String, JsonNode>> it = headers.fields();
            while (it.hasNext()) {
                Map.Entry<String, JsonNode> e = it.next();
                if (e.getKey().equalsIgnoreCase(name)) {
                    return e.getValue();
                }
            }
        }
        return null;
    }

    private static String urlDecode(String s) {
        try {
            return java.net.URLDecoder.decode(s, StandardCharsets.UTF_8.name());
        } catch (Exception e) {
            return s;
        }
    }

    private static byte[] readAll(InputStream in) throws IOException {
        ByteArrayOutputStream buf = new ByteArrayOutputStream();
        byte[] chunk = new byte[4096];
        int n;
        while ((n = in.read(chunk)) != -1) {
            buf.write(chunk, 0, n);
        }
        return buf.toByteArray();
    }
}
