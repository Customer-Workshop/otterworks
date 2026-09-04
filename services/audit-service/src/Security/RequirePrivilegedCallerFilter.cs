namespace OtterWorks.AuditService.Security;

/// <summary>
/// Rejects callers that are neither an admin nor an internal service principal. Applied to the
/// cross-user endpoints (compliance report, export, archive) that expose or destroy every user's
/// audit history.
/// </summary>
public sealed class RequirePrivilegedCallerFilter : IEndpointFilter
{
    public async ValueTask<object?> InvokeAsync(EndpointFilterInvocationContext context, EndpointFilterDelegate next)
    {
        if (!context.HttpContext.GetCaller().IsPrivileged)
        {
            return AuditResults.Forbidden();
        }

        return await next(context);
    }
}

public static class AuditResults
{
    public static IResult Forbidden() => Results.Json(
        new { error = "Caller is not allowed to access this audit data." },
        statusCode: StatusCodes.Status403Forbidden);
}
