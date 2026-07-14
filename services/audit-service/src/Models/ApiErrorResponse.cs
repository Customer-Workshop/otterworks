namespace OtterWorks.AuditService.Models;

public sealed record ApiError(string Code, string Message, int Status);

public sealed record ApiErrorResponse(ApiError Error)
{
    public static ApiErrorResponse Create(string code, string message, int status)
    {
        return new ApiErrorResponse(new ApiError(code, message, status));
    }
}
