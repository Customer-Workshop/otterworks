using OtterWorks.AuditService.Archive;

namespace OtterWorks.AuditService.Controllers;

/// <summary>
/// Retention history of an archived document from the selected ARCHIVE_STORE: the contract path
/// (/api/v1/audit/archive/{docId}, CONTRACTS §10.4) returns versions with nested events; the
/// /events routes return the flat FILEAUD list.
/// </summary>
public static class ArchiveController
{
    public static void MapArchiveEndpoints(this WebApplication app)
    {
        app.MapGet("/api/audit/archive/{docId}/events", GetEvents).WithName("GetArchiveEvents");
        app.MapGet("/api/v1/audit/archive/{docId}", GetDocument).WithName("GetArchiveDocumentV1");
        app.MapGet("/api/v1/audit/archive/{docId}/events", GetEvents).WithName("GetArchiveEventsV1Events");
        app.MapGet("/health/archive", ArchiveHealth).WithName("ArchiveHealth");
    }

    public static Task<IResult> GetEvents(string docId, ArchiveStoreRegistry registry, CancellationToken cancellationToken) =>
        WithStore(registry, async store =>
        {
            var events = await store.GetEventsAsync(docId, cancellationToken);
            if (events is null)
            {
                return NotFound(docId);
            }

            return Results.Ok(new ArchiveEventsResponse
            {
                DocId = Db2Text.RTrim(docId),
                Store = store.StoreName,
                Events = events,
            });
        });

    public static Task<IResult> GetDocument(string docId, ArchiveStoreRegistry registry, CancellationToken cancellationToken) =>
        WithStore(registry, async store =>
        {
            var versions = await store.GetDocumentAsync(docId, cancellationToken);
            if (versions is null)
            {
                return NotFound(docId);
            }

            return Results.Ok(new ArchiveDocumentResponse
            {
                DocId = Db2Text.RTrim(docId),
                Store = store.StoreName,
                Versions = versions,
            });
        });

    private static async Task<IResult> WithStore(ArchiveStoreRegistry registry, Func<IArchiveEventStore, Task<IResult>> read)
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
            return await read(store);
        }
        catch (ArchiveStoreUnavailableException ex)
        {
            return Unavailable(ex);
        }
    }

    private static IResult NotFound(string docId) =>
        Results.NotFound(new { error = "document not found", doc_id = Db2Text.RTrim(docId) });

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
