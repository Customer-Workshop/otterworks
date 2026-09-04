using OtterWorks.AuditService.Models;
using OtterWorks.AuditService.Security;
using OtterWorks.AuditService.Services;

namespace OtterWorks.AuditService.Controllers;

public static class AuditController
{
    public static void MapAuditEndpoints(this WebApplication app)
    {
        var group = app.MapGroup("/api/v1/audit")
            .AddEndpointFilter<CallerContextFilter>();

        group.MapPost("/events", RecordEvent)
            .WithName("RecordAuditEvent")
            .Produces<AuditEventResponse>(StatusCodes.Status201Created)
            .Produces(StatusCodes.Status400BadRequest)
            .Produces(StatusCodes.Status401Unauthorized)
            .Produces(StatusCodes.Status403Forbidden);

        group.MapGet("/events", QueryEvents)
            .WithName("QueryAuditEvents")
            .Produces<AuditEventPage>(StatusCodes.Status200OK)
            .Produces(StatusCodes.Status401Unauthorized)
            .Produces(StatusCodes.Status403Forbidden);

        group.MapGet("/events/{id}", GetEvent)
            .WithName("GetAuditEvent")
            .Produces<AuditEventResponse>(StatusCodes.Status200OK)
            .Produces(StatusCodes.Status401Unauthorized)
            .Produces(StatusCodes.Status404NotFound);

        group.MapGet("/reports/user/{userId}", GetUserActivityReport)
            .WithName("GetUserActivityReport")
            .Produces<UserActivityReport>(StatusCodes.Status200OK)
            .Produces(StatusCodes.Status401Unauthorized)
            .Produces(StatusCodes.Status403Forbidden);

        group.MapGet("/resources/{resourceId}/history", GetResourceHistory)
            .WithName("GetResourceHistory")
            .Produces<ResourceHistory>(StatusCodes.Status200OK)
            .Produces(StatusCodes.Status401Unauthorized);

        group.MapGet("/reports/compliance", GetComplianceReport)
            .WithName("GetComplianceReport")
            .AddEndpointFilter<RequirePrivilegedCallerFilter>()
            .Produces<ComplianceReport>(StatusCodes.Status200OK)
            .Produces(StatusCodes.Status401Unauthorized)
            .Produces(StatusCodes.Status403Forbidden);

        group.MapGet("/export", ExportAuditLog)
            .WithName("ExportAuditLog")
            .AddEndpointFilter<RequirePrivilegedCallerFilter>()
            .Produces<ExportResult>(StatusCodes.Status200OK)
            .Produces(StatusCodes.Status401Unauthorized)
            .Produces(StatusCodes.Status403Forbidden);

        group.MapPost("/archive", ArchiveOldEvents)
            .WithName("ArchiveOldEvents")
            .AddEndpointFilter<RequirePrivilegedCallerFilter>()
            .Produces<ArchiveResult>(StatusCodes.Status200OK)
            .Produces(StatusCodes.Status401Unauthorized)
            .Produces(StatusCodes.Status403Forbidden);
    }

    private static async Task<IResult> RecordEvent(
        AuditEventRequest request,
        HttpContext httpContext,
        IAuditService auditService)
    {
        var caller = httpContext.GetCaller();

        if (!caller.IsPrivileged)
        {
            if (!string.IsNullOrWhiteSpace(request.UserId) &&
                !string.Equals(request.UserId, caller.UserId, StringComparison.Ordinal))
            {
                return AuditResults.Forbidden();
            }

            request.UserId = caller.UserId;
        }

        if (string.IsNullOrWhiteSpace(request.UserId) ||
            string.IsNullOrWhiteSpace(request.Action) ||
            string.IsNullOrWhiteSpace(request.ResourceType) ||
            string.IsNullOrWhiteSpace(request.ResourceId))
        {
            return Results.BadRequest(new { error = "UserId, Action, ResourceType, and ResourceId are required." });
        }

        var response = await auditService.RecordEventAsync(request);
        return Results.Created($"/api/v1/audit/events/{response.Id}", response);
    }

    private static async Task<IResult> QueryEvents(
        string? user_id,
        string? action,
        string? resource,
        string? resource_type,
        DateTime? from,
        DateTime? to,
        int? page,
        int? size,
        HttpContext httpContext,
        IAuditService auditService)
    {
        var caller = httpContext.GetCaller();
        var callerUserId = user_id;

        if (!caller.IsPrivileged)
        {
            if (!string.IsNullOrWhiteSpace(user_id) &&
                !string.Equals(user_id, caller.UserId, StringComparison.Ordinal))
            {
                return AuditResults.Forbidden();
            }

            callerUserId = caller.UserId;
        }

        var pageNumber = page ?? 1;
        var pageSize = Math.Clamp(size ?? 20, 1, 100);

        var result = await auditService.QueryEventsAsync(callerUserId, action, resource_type, resource, from, to, pageNumber, pageSize);
        return Results.Ok(result);
    }

    private static async Task<IResult> GetEvent(
        string id,
        HttpContext httpContext,
        IAuditService auditService)
    {
        var caller = httpContext.GetCaller();
        var result = await auditService.GetEventAsync(id);

        // Events belonging to other users are hidden behind the existing 404 convention.
        if (result is null || (!caller.IsPrivileged && !string.Equals(result.UserId, caller.UserId, StringComparison.Ordinal)))
        {
            return Results.NotFound(new { error = "Event not found." });
        }

        return Results.Ok(result);
    }

    private static async Task<IResult> GetUserActivityReport(
        string userId,
        string? period,
        HttpContext httpContext,
        IAuditService auditService)
    {
        var caller = httpContext.GetCaller();
        if (!caller.IsPrivileged && !string.Equals(userId, caller.UserId, StringComparison.Ordinal))
        {
            return AuditResults.Forbidden();
        }

        var reportPeriod = period ?? "30d";
        var report = await auditService.GetUserActivityReportAsync(userId, reportPeriod);
        return Results.Ok(report);
    }

    private static async Task<IResult> GetResourceHistory(
        string resourceId,
        HttpContext httpContext,
        IAuditService auditService)
    {
        // audit-service stores no owner for the referenced resource, so unprivileged callers only
        // ever see the part of a resource's history they themselves generated.
        var caller = httpContext.GetCaller();
        var restrictToUserId = caller.IsPrivileged ? null : caller.UserId;

        var history = await auditService.GetResourceHistoryAsync(resourceId, restrictToUserId);
        return Results.Ok(history);
    }

    private static async Task<IResult> GetComplianceReport(
        string? period,
        IAuditService auditService)
    {
        var reportPeriod = period ?? "30d";
        var report = await auditService.GetComplianceReportAsync(reportPeriod);
        return Results.Ok(report);
    }

    private static async Task<IResult> ExportAuditLog(
        string? format,
        DateTime? from,
        DateTime? to,
        IAuditService auditService)
    {
        var exportFormat = format ?? "json";
        var exportFrom = from ?? DateTime.UtcNow.AddDays(-30);
        var exportTo = to ?? DateTime.UtcNow;

        if (!string.Equals(exportFormat, "csv", StringComparison.OrdinalIgnoreCase) &&
            !string.Equals(exportFormat, "json", StringComparison.OrdinalIgnoreCase))
        {
            return Results.BadRequest(new { error = "Format must be 'csv' or 'json'." });
        }

        var result = await auditService.ExportAsync(exportFrom, exportTo, exportFormat);
        return Results.Ok(result);
    }

    private static async Task<IResult> ArchiveOldEvents(
        IAuditService auditService)
    {
        var result = await auditService.ArchiveOldEventsAsync();
        return Results.Ok(result);
    }
}
