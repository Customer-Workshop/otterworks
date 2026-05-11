using Microsoft.AspNetCore.Http;
using OtterWorks.ApiGateway.Middleware;

namespace ApiGateway.Tests.Unit;

public class RequestIdMiddlewareTests
{
    [Fact]
    public async Task GeneratesUUID_WhenNoHeaderPresent()
    {
        string? capturedId = null;
        var middleware = new RequestIdMiddleware(context =>
        {
            capturedId = RequestIdMiddleware.GetRequestId(context);
            context.Response.StatusCode = 200;
            return Task.CompletedTask;
        });

        var context = new DefaultHttpContext();

        await middleware.InvokeAsync(context);

        Assert.NotNull(capturedId);
        Assert.NotEmpty(capturedId);
        Assert.Equal(200, context.Response.StatusCode);
        Assert.NotEmpty(context.Response.Headers["X-Request-ID"].ToString());
    }

    [Fact]
    public async Task PropagatesExisting_WhenHeaderPresent()
    {
        const string existingId = "existing-request-id-123";
        string? capturedId = null;
        var middleware = new RequestIdMiddleware(context =>
        {
            capturedId = RequestIdMiddleware.GetRequestId(context);
            context.Response.StatusCode = 200;
            return Task.CompletedTask;
        });

        var context = new DefaultHttpContext();
        context.Request.Headers["X-Request-ID"] = existingId;

        await middleware.InvokeAsync(context);

        Assert.Equal(existingId, capturedId);
        Assert.Equal(existingId, context.Response.Headers["X-Request-ID"].ToString());
    }

    [Fact]
    public void GetRequestId_EmptyContext_ReturnsEmpty()
    {
        var context = new DefaultHttpContext();
        var id = RequestIdMiddleware.GetRequestId(context);
        Assert.Equal(string.Empty, id);
    }
}
