using System.Text.Json;
using OtterWorks.FileService.Models;

namespace OtterWorks.FileService.Middleware;

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
            _logger.LogError(ex, "Unhandled exception");
            context.Response.StatusCode = 500;
            context.Response.ContentType = "application/json";
            var error = new ErrorResponse
            {
                Error = "internal_error",
                Message = "An internal error occurred",
            };
            await context.Response.WriteAsync(JsonSerializer.Serialize(error));
        }
    }
}
