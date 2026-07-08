using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging;
using Moq;
using OtterWorks.AuditService.Middleware;

namespace AuditService.Tests;

public class RequestLoggingMiddlewareTests
{
    private readonly Mock<ILogger<RequestLoggingMiddleware>> _mockLogger = new();

    [Fact]
    public async Task InvokeAsync_WhenNextSucceeds_CallsNextAndLogsInformation()
    {
        var context = new DefaultHttpContext();
        context.Request.Method = "GET";
        context.Request.Path = "/api/v1/audit/events";
        var nextCalled = false;

        var middleware = new RequestLoggingMiddleware(_ =>
        {
            nextCalled = true;
            return Task.CompletedTask;
        }, _mockLogger.Object);

        await middleware.InvokeAsync(context);

        Assert.True(nextCalled);
        VerifyLogged(LogLevel.Information);
    }

    [Fact]
    public async Task InvokeAsync_WhenNextThrows_LogsErrorAndRethrows()
    {
        var context = new DefaultHttpContext();
        context.Request.Method = "POST";
        context.Request.Path = "/api/v1/audit/events";

        var middleware = new RequestLoggingMiddleware(
            _ => throw new InvalidOperationException("downstream failure"),
            _mockLogger.Object);

        await Assert.ThrowsAsync<InvalidOperationException>(() => middleware.InvokeAsync(context));

        VerifyLogged(LogLevel.Error);
    }

    private void VerifyLogged(LogLevel level) =>
        _mockLogger.Verify(
            l => l.Log(
                level,
                It.IsAny<EventId>(),
                It.IsAny<It.IsAnyType>(),
                It.IsAny<Exception?>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once);
}
