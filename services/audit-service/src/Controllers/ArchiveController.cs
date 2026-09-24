using OtterWorks.AuditService.Archive;

namespace OtterWorks.AuditService.Controllers;

/// <summary>
/// FILEAUD events for an archived document from the selected ARCHIVE_STORE, exposed under the
/// gateway path (/api/audit/...) and the contract path (/api/v1/audit/archive/{docId}).
/// </summary>
public static class ArchiveController
{
    public static void MapArchiveEndpoints(this WebApplication app)
    {
        app.MapGet("/api/audit/archive/{docId}/events", GetEvents).WithName("GetArchiveEvents");
        app.MapGet("/api/v1/audit/archive/{docId}", GetEvents).WithName("GetArchiveEventsV1");
        app.MapGet("/api/v1/audit/archive/{docId}/events", GetEvents).WithName("GetArchiveEventsV1Events");
        app.MapGet("/health/archive", ArchiveHealth).WithName("ArchiveHealth");
    }

    public static async Task<IResult> GetEvents(string docId, ArchiveStoreRegistry registry, CancellationToken cancellationToken)
    {
        IArchiveEventStore store;
        try
        {
            store = registry.Store;
        }
        catch (ArchiveFeatureDisabledException)
        {
            return Results.NotFound(new { error = "archive feature is not enabled", hint = ArchiveFeatureDisabledException.Hint });
        }
        catch (ArchiveStoreUnavailableException ex)
        {
            return Unavailable(ex);
        }

        try
        {
            var events = await store.GetEventsAsync(docId, cancellationToken);
            if (events is null)
            {
                return Results.NotFound(new { error = "document not found", doc_id = Db2Text.RTrim(docId) });
            }

            return Results.Ok(new ArchiveEventsResponse
            {
                DocId = Db2Text.RTrim(docId),
                Store = store.StoreName,
                Events = events,
            });
        }
        catch (ArchiveStoreUnavailableException ex)
        {
            return Unavailable(ex);
        }
    }

    public static async Task<IResult> ArchiveHealth(ArchiveStoreRegistry registry, CancellationToken cancellationToken)
    {
        var store = registry.Type switch
        {
            ArchiveStoreType.Off => "off",
            ArchiveStoreType.Db2 => "db2",
            ArchiveStoreType.AzureSql => "azuresql",
            _ => "invalid",
        };
        if (registry.Type == ArchiveStoreType.Off)
        {
            return Results.Ok(new { status = "disabled", store, @namespace = registry.Namespace });
        }

        try
        {
            await registry.Store.PingAsync(cancellationToken);
            return Results.Ok(new { status = "healthy", store, @namespace = registry.Namespace });
        }
        catch (ArchiveStoreUnavailableException ex)
        {
            return Results.Json(
                new { status = "unavailable", store, @namespace = registry.Namespace, detail = ex.Message },
                statusCode: StatusCodes.Status503ServiceUnavailable);
        }
    }

    private static IResult Unavailable(ArchiveStoreUnavailableException ex) =>
        Results.Json(new { error = "archive store unavailable", detail = ex.Message }, statusCode: StatusCodes.Status503ServiceUnavailable);
}
