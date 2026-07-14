using System.Net;
using System.Text.Json;
using OtterWorks.AuditService.Models;

namespace OtterWorks.AuditService.Middleware;

public class ErrorHandlingMiddleware
{
    private readonly RequestDelegate _next;
    private readonly ILogger<ErrorHandlingMiddleware> _logger;

    public ErrorHandlingMiddleware(RequestDelegate next, ILogger<ErrorHandlingMiddleware> logger)
    {
        _next = next;
        _logger = logger;
    }

    public async Task InvokeAsync(HttpContext context)
    {
        try
        {
            await _next(context);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Unhandled exception processing {Method} {Path}",
                context.Request.Method, context.Request.Path);

            if (context.Response.HasStarted)
            {
                _logger.LogWarning("Response has already started, cannot write error response");
                throw;
            }

            context.Response.StatusCode = (int)HttpStatusCode.InternalServerError;
            context.Response.ContentType = "application/json";

            var errorResponse = ApiErrorResponse.Create(
                "INTERNAL_ERROR",
                "An internal server error occurred.",
                context.Response.StatusCode);

            var json = JsonSerializer.Serialize(
                errorResponse,
                new JsonSerializerOptions(JsonSerializerDefaults.Web));
            await context.Response.WriteAsync(json);
        }
    }
}
