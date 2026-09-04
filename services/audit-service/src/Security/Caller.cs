namespace OtterWorks.AuditService.Security;

/// <summary>The authenticated principal behind a request, resolved from the gateway-injected X-User-ID header.</summary>
public sealed record Caller(string UserId, bool IsAdmin, bool IsServiceAccount)
{
    /// <summary>True when the caller may act on audit data belonging to other users.</summary>
    public bool IsPrivileged => IsAdmin || IsServiceAccount;
}

public static class CallerHttpContextExtensions
{
    public const string HeaderName = "X-User-ID";
    internal const string ItemKey = "audit.caller";

    /// <summary>Returns the caller resolved by <see cref="CallerContextFilter"/>.</summary>
    public static Caller GetCaller(this HttpContext context)
    {
        return context.Items[ItemKey] as Caller
            ?? throw new InvalidOperationException(
                $"No caller in context. Endpoints must be protected by {nameof(CallerContextFilter)}.");
    }
}
