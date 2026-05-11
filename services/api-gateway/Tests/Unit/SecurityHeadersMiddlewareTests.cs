using Microsoft.AspNetCore.Http;
using OtterWorks.ApiGateway.Middleware;

namespace ApiGateway.Tests.Unit;

public class SecurityHeadersMiddlewareTests
{
    [Fact]
    public async Task AddsSecurityHeaders()
    {
        var middleware = new SecurityHeadersMiddleware(context =>
        {
            context.Response.StatusCode = 200;
            return Task.CompletedTask;
        });

        var context = new DefaultHttpContext();

        await middleware.InvokeAsync(context);

        Assert.Equal("DENY", context.Response.Headers["X-Frame-Options"].ToString());
        Assert.Equal("nosniff", context.Response.Headers["X-Content-Type-Options"].ToString());
        Assert.Equal("1; mode=block", context.Response.Headers["X-XSS-Protection"].ToString());
    }
}
