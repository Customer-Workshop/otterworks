using System.Text.Json;
using Microsoft.Extensions.Options;
using OtterWorks.SearchService.Configuration;
namespace OtterWorks.SearchService.Middleware;

public class AuthMiddleware
{
    private readonly RequestDelegate _next;
    private readonly AuthSettings _authSettings;
    private readonly Serilog.ILogger _logger = Serilog.Log.ForContext<AuthMiddleware>();

    private static readonly string[] PublicPrefixes = { "/health", "/metrics", "/swagger" };

    public AuthMiddleware(RequestDelegate next, IOptions<AuthSettings> authSettings)
    {
        _next = next;
        _authSettings = authSettings.Value;
    }

    public async Task InvokeAsync(HttpContext context)
    {
        if (!_authSettings.RequireAuth)
        {
            await _next(context);
            return;
        }

        string path = context.Request.Path.Value ?? string.Empty;
        if (PublicPrefixes.Any(p => path.StartsWith(p, StringComparison.OrdinalIgnoreCase)))
        {
            await _next(context);
            return;
        }

        if (!string.IsNullOrEmpty(_authSettings.ServiceToken))
        {
            string? token = ExtractBearerToken(context);
            if (token == _authSettings.ServiceToken)
            {
                await _next(context);
                return;
            }
        }

        string userId = context.Request.Headers["X-User-ID"].ToString().Trim();
        if (!string.IsNullOrEmpty(userId))
        {
            await _next(context);
            return;
        }

        _logger.Warning("Auth rejected: {Path}", path);
        context.Response.StatusCode = 401;
        context.Response.ContentType = "application/json";
        await context.Response.WriteAsync(JsonSerializer.Serialize(new { error = "unauthorized" }));
    }

    private static string? ExtractBearerToken(HttpContext context)
    {
        string authHeader = context.Request.Headers.Authorization.ToString();
        if (authHeader.StartsWith("Bearer ", StringComparison.OrdinalIgnoreCase))
            return authHeader[7..].Trim();
        return null;
    }
}
