package com.otterworks.report.lambda;

import com.amazonaws.services.lambda.runtime.ClientContext;
import com.amazonaws.services.lambda.runtime.CognitoIdentity;
import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.LambdaLogger;

/**
 * Minimal {@link Context} used only by {@link LocalApiGatewayRunner} so the
 * exact Lambda code path (the {@link StreamLambdaHandler} proxy stream) can be
 * exercised locally when real AWS Lambda is not reachable from the environment.
 * Not used by the deployed Lambda, which receives a real runtime context.
 */
class SimpleLambdaContext implements Context {

    @Override
    public String getAwsRequestId() {
        return "local-" + Long.toHexString(System.nanoTime());
    }

    @Override
    public String getLogGroupName() {
        return "/aws/lambda/local";
    }

    @Override
    public String getLogStreamName() {
        return "local";
    }

    @Override
    public String getFunctionName() {
        return "report-service-lambda-local";
    }

    @Override
    public String getFunctionVersion() {
        return "$LATEST";
    }

    @Override
    public String getInvokedFunctionArn() {
        return "arn:aws:lambda:local:000000000000:function:report-service-lambda-local";
    }

    @Override
    public CognitoIdentity getIdentity() {
        return null;
    }

    @Override
    public ClientContext getClientContext() {
        return null;
    }

    @Override
    public int getRemainingTimeInMillis() {
        return 30000;
    }

    @Override
    public int getMemoryLimitInMB() {
        return 1024;
    }

    @Override
    public LambdaLogger getLogger() {
        return new LambdaLogger() {
            @Override
            public void log(String message) {
                System.out.print(message);
            }

            @Override
            public void log(byte[] message) {
                System.out.write(message, 0, message.length);
            }
        };
    }
}
