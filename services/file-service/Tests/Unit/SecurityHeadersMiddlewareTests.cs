using Microsoft.AspNetCore.Http;
using OtterWorks.FileService.Middleware;

namespace FileService.Tests.Unit;

public class SecurityHeadersMiddlewareTests
{
    [Fact]
    public async Task AddsSecurityHeaders()
    {
        var context = new DefaultHttpContext();
        var middleware = new SecurityHeadersMiddleware(_ => Task.CompletedTask);

        await middleware.InvokeAsync(context);

        Assert.Equal("DENY", context.Response.Headers["X-Frame-Options"]);
        Assert.Equal("nosniff", context.Response.Headers["X-Content-Type-Options"]);
        Assert.Equal("1; mode=block", context.Response.Headers["X-XSS-Protection"]);
    }
}
