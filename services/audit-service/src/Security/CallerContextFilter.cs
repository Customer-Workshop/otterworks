using Microsoft.Extensions.Options;

namespace OtterWorks.AuditService.Security;

/// <summary>
/// Resolves the authenticated caller from the gateway-injected X-User-ID header and makes it
/// available to handlers via <see cref="CallerHttpContextExtensions.GetCaller"/>.
/// Requests without a usable header are rejected as unauthenticated.
/// </summary>
public sealed class CallerContextFilter : IEndpointFilter
{
    private readonly AuthorizationSettings _settings;

    public CallerContextFilter(IOptions<AuthorizationSettings> settings)
    {
        _settings = settings.Value;
    }

    public async ValueTask<object?> InvokeAsync(EndpointFilterInvocationContext context, EndpointFilterDelegate next)
    {
        var header = context.HttpContext.Request.Headers[CallerHttpContextExtensions.HeaderName].ToString();
        var userId = header.Trim();

        if (string.IsNullOrEmpty(userId))
        {
            return Results.Json(
                new { error = $"Missing or invalid {CallerHttpContextExtensions.HeaderName} header." },
                statusCode: StatusCodes.Status401Unauthorized);
        }

        context.HttpContext.Items[CallerHttpContextExtensions.ItemKey] = new Caller(
            userId,
            IsAdmin: _settings.AdminUserIds.Contains(userId, StringComparer.Ordinal),
            IsServiceAccount: _settings.ServiceAccountIds.Contains(userId, StringComparer.Ordinal));

        return await next(context);
    }
}
