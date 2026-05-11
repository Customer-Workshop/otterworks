using System.Diagnostics;

namespace OtterWorks.FileService.Middleware;

public class RequestLoggingMiddleware
{
    private readonly RequestDelegate _next;
    private readonly ILogger<RequestLoggingMiddleware> _logger;

    public RequestLoggingMiddleware(RequestDelegate next, ILogger<RequestLoggingMiddleware> logger)
    {
        _next = next;
        _logger = logger;
    }

    public async Task InvokeAsync(HttpContext context)
    {
        var requestId = context.Request.Headers["x-request-id"].FirstOrDefault() ?? Guid.NewGuid().ToString();
        context.Response.Headers["x-request-id"] = requestId;

        var stopwatch = Stopwatch.StartNew();
        await _next(context);
        stopwatch.Stop();

        _logger.LogInformation(
            "Request completed: {Method} {Path} {StatusCode} {DurationMs}ms RequestId={RequestId}",
            context.Request.Method,
            context.Request.Path,
            context.Response.StatusCode,
            stopwatch.ElapsedMilliseconds,
            requestId);
    }
}
