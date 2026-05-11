using Microsoft.Extensions.Options;
using OtterWorks.SearchService.Config;

namespace OtterWorks.SearchService.Middleware;

public class AuthMiddleware
{
    private static readonly string[] PublicPrefixes = ["/health", "/metrics"];
    private readonly RequestDelegate _next;
    private readonly AuthSettings _settings;
    private readonly ILogger<AuthMiddleware> _logger;

    public AuthMiddleware(RequestDelegate next, IOptions<AuthSettings> settings, ILogger<AuthMiddleware> logger)
    {
        _next = next;
        _settings = settings.Value;
        _logger = logger;
    }

    public async Task InvokeAsync(HttpContext context)
    {
        if (!_settings.RequireAuth)
        {
            await _next(context);
            return;
        }

        var path = context.Request.Path.Value ?? string.Empty;
        if (PublicPrefixes.Any(p => path.StartsWith(p, StringComparison.OrdinalIgnoreCase)))
        {
            await _next(context);
            return;
        }

        if (!string.IsNullOrEmpty(_settings.ServiceToken))
        {
            var token = ExtractBearerToken(context);
            if (!string.IsNullOrEmpty(token) && token == _settings.ServiceToken)
            {
                await _next(context);
                return;
            }
        }

        var userId = context.Request.Headers["X-User-ID"].FirstOrDefault()?.Trim();
        if (!string.IsNullOrEmpty(userId))
        {
            await _next(context);
            return;
        }

        _logger.LogWarning("Auth rejected: {Path}", path);
        context.Response.StatusCode = 401;
        context.Response.ContentType = "application/json";
        await context.Response.WriteAsync("{\"error\":\"unauthorized\"}");
    }

    private static string ExtractBearerToken(HttpContext context)
    {
        var authHeader = context.Request.Headers.Authorization.FirstOrDefault() ?? string.Empty;
        if (authHeader.StartsWith("Bearer ", StringComparison.OrdinalIgnoreCase))
        {
            return authHeader[7..].Trim();
        }

        return string.Empty;
    }
}
