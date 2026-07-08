using System.Text.Json;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging;
using Moq;
using OtterWorks.AuditService.Middleware;

namespace AuditService.Tests;

public class ErrorHandlingMiddlewareTests
{
    private readonly Mock<ILogger<ErrorHandlingMiddleware>> _mockLogger = new();

    [Fact]
    public async Task InvokeAsync_WhenNextSucceeds_DoesNotAlterResponse()
    {
        var context = new DefaultHttpContext();
        var nextCalled = false;
        var middleware = new ErrorHandlingMiddleware(_ =>
        {
            nextCalled = true;
            return Task.CompletedTask;
        }, _mockLogger.Object);

        await middleware.InvokeAsync(context);

        Assert.True(nextCalled);
        Assert.Equal(StatusCodes.Status200OK, context.Response.StatusCode);
    }

    [Fact]
    public async Task InvokeAsync_WhenNextThrows_Writes500JsonProblem()
    {
        var context = new DefaultHttpContext();
        context.TraceIdentifier = "trace-123";
        var responseBody = new MemoryStream();
        context.Response.Body = responseBody;

        var middleware = new ErrorHandlingMiddleware(
            _ => throw new InvalidOperationException("kaboom"),
            _mockLogger.Object);

        await middleware.InvokeAsync(context);

        Assert.Equal(StatusCodes.Status500InternalServerError, context.Response.StatusCode);
        Assert.Equal("application/json", context.Response.ContentType);

        responseBody.Position = 0;
        using var doc = JsonDocument.Parse(responseBody);
        Assert.Equal("An internal server error occurred.", doc.RootElement.GetProperty("error").GetString());
        Assert.Equal("trace-123", doc.RootElement.GetProperty("traceId").GetString());
    }

    [Fact]
    public async Task InvokeAsync_WhenResponseAlreadyStarted_Rethrows()
    {
        var context = new DefaultHttpContext();
        var responseFeature = new StartedResponseFeature();
        context.Features.Set<Microsoft.AspNetCore.Http.Features.IHttpResponseFeature>(responseFeature);

        var middleware = new ErrorHandlingMiddleware(
            _ => throw new InvalidOperationException("kaboom"),
            _mockLogger.Object);

        await Assert.ThrowsAsync<InvalidOperationException>(() => middleware.InvokeAsync(context));
    }

    private sealed class StartedResponseFeature : Microsoft.AspNetCore.Http.Features.IHttpResponseFeature
    {
        public Stream Body { get; set; } = new MemoryStream();
        public bool HasStarted => true;
        public IHeaderDictionary Headers { get; set; } = new HeaderDictionary();
        public string? ReasonPhrase { get; set; }
        public int StatusCode { get; set; } = 200;

        public void OnCompleted(Func<object, Task> callback, object state)
        {
        }

        public void OnStarting(Func<object, Task> callback, object state)
        {
        }
    }
}
