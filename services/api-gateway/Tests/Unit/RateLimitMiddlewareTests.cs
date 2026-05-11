using Microsoft.AspNetCore.Http;
using OtterWorks.ApiGateway.Middleware;

namespace ApiGateway.Tests.Unit;

public class RateLimitMiddlewareTests
{
    [Fact]
    public void Allow_FirstRequestsAllowed()
    {
        var rl = new RateLimiter(5);

        for (var i = 0; i < 5; i++)
        {
            Assert.True(rl.Allow("192.168.1.1"), $"Request {i + 1} should be allowed");
        }

        Assert.False(rl.Allow("192.168.1.1"), "6th request should be denied");
        Assert.True(rl.Allow("192.168.1.2"), "Different IP should be allowed");
    }

    [Fact]
    public void Allow_TokenRefill()
    {
        var rl = new RateLimiter(2);
        var now = DateTime.UtcNow;
        rl.Now = () => now;

        Assert.True(rl.Allow("10.0.0.1"));
        Assert.True(rl.Allow("10.0.0.1"));
        Assert.False(rl.Allow("10.0.0.1"));

        rl.Now = () => now.AddSeconds(1);
        Assert.True(rl.Allow("10.0.0.1"));
        Assert.True(rl.Allow("10.0.0.1"));
        Assert.False(rl.Allow("10.0.0.1"));
    }

    [Fact]
    public async Task Handler_RateLimitsRequests()
    {
        var rl = new RateLimiter(2);
        var middleware = new RateLimitMiddleware(
            context =>
            {
                context.Response.StatusCode = 200;
                return Task.CompletedTask;
            },
            rl);

        for (var i = 0; i < 2; i++)
        {
            var context = new DefaultHttpContext();
            context.Connection.RemoteIpAddress = System.Net.IPAddress.Parse("192.168.1.1");

            await middleware.InvokeAsync(context);
            Assert.Equal(200, context.Response.StatusCode);
        }

        var limitedContext = new DefaultHttpContext();
        limitedContext.Connection.RemoteIpAddress = System.Net.IPAddress.Parse("192.168.1.1");

        await middleware.InvokeAsync(limitedContext);
        Assert.Equal(429, limitedContext.Response.StatusCode);
        Assert.Equal("1", limitedContext.Response.Headers["Retry-After"].ToString());
    }

    [Theory]
    [InlineData("10.0.0.1", null, "10.0.0.1")]
    [InlineData("10.0.0.1", "203.0.113.50", "203.0.113.50")]
    public void ExtractIp_ExtractsCorrectly(string remoteIp, string? forwardedFor, string expected)
    {
        var context = new DefaultHttpContext();
        context.Connection.RemoteIpAddress = System.Net.IPAddress.Parse(remoteIp);
        if (forwardedFor != null)
        {
            context.Request.Headers["X-Forwarded-For"] = forwardedFor;
        }

        var result = RateLimitMiddleware.ExtractIp(context);
        Assert.Equal(expected, result);
    }
}
