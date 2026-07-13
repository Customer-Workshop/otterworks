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
 * AWS Lambda entry point that wraps the existing Spring Boot application.
 *
 * The same {@link ReportApplication} context (controllers, services, JPA
 * repositories) that runs as an always-on EKS pod is booted once per Lambda
 * execution environment and API Gateway proxy events are dispatched straight
 * to Spring MVC. The HTTP contract is therefore identical to the container
 * deployment — this is a packaging change, not an API rewrite.
 *
 * Binary response handling is left to API Gateway configuration for now.
 */
public class StreamLambdaHandler implements RequestStreamHandler {

    private static final SpringBootLambdaContainerHandler<AwsProxyRequest, AwsProxyResponse> HANDLER;

    static {
        try {
            HANDLER = SpringBootLambdaContainerHandler.getAwsProxyHandler(ReportApplication.class);
            HANDLER.onStartup(servletContext -> { });
        } catch (ContainerInitializationException e) {
            throw new RuntimeException("Could not initialize Spring Boot application", e);
        }
    }

    @Override
    public void handleRequest(InputStream input, OutputStream output, Context context) throws IOException {
        HANDLER.proxyStream(input, output, context);
    }
}
