using System.Diagnostics;

namespace OtterWorks.ApiGateway.Middleware;

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
        var stopwatch = Stopwatch.StartNew();
        var requestPath = context.Request.Path;
        var method = context.Request.Method;
        var requestId = RequestIdMiddleware.GetRequestId(context);

        try
        {
            await _next(context);
            stopwatch.Stop();

            var statusCode = context.Response.StatusCode;
            if (statusCode >= 500)
            {
                _logger.LogError(
                    "HTTP {Method} {Path} responded {StatusCode} in {ElapsedMs}ms [request_id={RequestId}]",
                    method, requestPath, statusCode, stopwatch.ElapsedMilliseconds, requestId);
            }
            else if (statusCode >= 400)
            {
                _logger.LogWarning(
                    "HTTP {Method} {Path} responded {StatusCode} in {ElapsedMs}ms [request_id={RequestId}]",
                    method, requestPath, statusCode, stopwatch.ElapsedMilliseconds, requestId);
            }
            else
            {
                _logger.LogInformation(
                    "HTTP {Method} {Path} responded {StatusCode} in {ElapsedMs}ms [request_id={RequestId}]",
                    method, requestPath, statusCode, stopwatch.ElapsedMilliseconds, requestId);
            }
        }
        catch (Exception ex)
        {
            stopwatch.Stop();
            _logger.LogError(ex,
                "HTTP {Method} {Path} failed after {ElapsedMs}ms [request_id={RequestId}]",
                method, requestPath, stopwatch.ElapsedMilliseconds, requestId);
            throw;
        }
    }
}
