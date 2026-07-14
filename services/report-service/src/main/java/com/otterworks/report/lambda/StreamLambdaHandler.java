package com.otterworks.report.lambda;

import com.amazonaws.serverless.proxy.model.AwsProxyRequest;
import com.amazonaws.serverless.proxy.model.AwsProxyResponse;
import com.amazonaws.serverless.proxy.spring.SpringBootLambdaContainerHandler;
import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestStreamHandler;
import com.amazonaws.services.secretsmanager.AWSSecretsManager;
import com.amazonaws.services.secretsmanager.AWSSecretsManagerClientBuilder;
import com.amazonaws.services.secretsmanager.model.GetSecretValueRequest;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.otterworks.report.ReportApplication;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

/** AWS Lambda entry point for the existing Spring Boot application. */
public class StreamLambdaHandler implements RequestStreamHandler {

    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();
    private static final SpringBootLambdaContainerHandler<AwsProxyRequest, AwsProxyResponse> HANDLER;

    static {
        try {
            configureDatabaseCredentials();
            HANDLER = SpringBootLambdaContainerHandler.getAwsProxyHandler(ReportApplication.class);
            HANDLER.onStartup(servletContext -> { });
        } catch (Exception e) {
            throw new RuntimeException("Could not initialize Spring Boot application", e);
        }
    }

    private static void configureDatabaseCredentials() throws IOException {
        String secretArn = System.getenv("DB_SECRET_ARN");
        if (secretArn == null || secretArn.trim().isEmpty()) {
            return;
        }

        AWSSecretsManager secretsManager = AWSSecretsManagerClientBuilder.defaultClient();
        try {
            String secretString = secretsManager.getSecretValue(
                    new GetSecretValueRequest().withSecretId(secretArn)).getSecretString();
            JsonNode secret = OBJECT_MAPPER.readTree(secretString);
            System.setProperty("spring.datasource.username", requiredText(secret, "username"));
            System.setProperty("spring.datasource.password", requiredText(secret, "password"));
        } finally {
            secretsManager.shutdown();
        }
    }

    private static String requiredText(JsonNode secret, String fieldName) {
        JsonNode value = secret.get(fieldName);
        if (value == null || value.asText().trim().isEmpty()) {
            throw new IllegalStateException("Database secret is missing " + fieldName);
        }
        return value.asText();
    }

    @Override
    public void handleRequest(InputStream input, OutputStream output, Context context) throws IOException {
        HANDLER.proxyStream(input, output, context);
    }
}
