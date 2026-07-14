package com.otterworks.report.lambda;

import com.amazonaws.serverless.exceptions.ContainerInitializationException;
import com.amazonaws.serverless.proxy.model.AwsProxyRequest;
import com.amazonaws.serverless.proxy.model.AwsProxyResponse;
import com.amazonaws.serverless.proxy.spring.SpringBootLambdaContainerHandler;
import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestStreamHandler;
import com.otterworks.report.ReportApplication;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

/**
 * AWS Lambda entry point for the report-service.
 *
 * This is the ONLY new production code the serverless (Lambda + API Gateway)
 * migration adds: it wraps the EXISTING Spring Boot application
 * ({@link ReportApplication}) with AWS Serverless Java Container so the same
 * controllers, routes, and response schemas are served behind API Gateway.
 * No business logic, controller, or contract changes are made — the migration
 * is a hosting/packaging swap, and the always-on EKS deployment stays the
 * default on {@code main}.
 *
 * <p>Handler string for the Lambda function:
 * {@code com.otterworks.report.lambda.StreamLambdaHandler::handleRequest}
 */
public class StreamLambdaHandler implements RequestStreamHandler {

    private static final SpringBootLambdaContainerHandler<AwsProxyRequest, AwsProxyResponse> HANDLER;

    static {
        try {
            // Activate the "lambda" profile so application-lambda.properties (the
            // connection-layer overlay for serverless) applies. No default-profile
            // config — and therefore nothing on `main` — is affected.
            HANDLER = SpringBootLambdaContainerHandler.getAwsProxyHandler(ReportApplication.class, "lambda");
        } catch (ContainerInitializationException e) {
            // Fail fast during cold start so the invocation surfaces the real cause.
            throw new RuntimeException("Could not initialize Spring Boot application for Lambda", e);
        }
    }

    @Override
    public void handleRequest(InputStream input, OutputStream output, Context context) throws IOException {
        HANDLER.proxyStream(input, output, context);
    }
}
