using Microsoft.AspNetCore.Mvc;
using OtterWorks.SearchService.Models;
using OtterWorks.SearchService.Services;

namespace OtterWorks.SearchService.Controllers;

public static class SearchEndpoints
{
    public static void MapSearchEndpoints(this WebApplication app)
    {
        var group = app.MapGroup("/api/v1/search");

        group.MapGet("/", SearchDocuments).WithName("SearchDocuments");
        group.MapGet("/suggest", Suggest).WithName("Suggest");
        group.MapPost("/advanced", AdvancedSearch).WithName("AdvancedSearch");
        group.MapGet("/analytics", GetAnalytics).WithName("GetAnalytics");
        group.MapPost("/index/document", IndexDocument).WithName("IndexDocument");
        group.MapPost("/index/file", IndexFile).WithName("IndexFile");
        group.MapDelete("/index/{docType}/{docId}", RemoveFromIndex).WithName("RemoveFromIndex");
        group.MapPost("/reindex", Reindex).WithName("Reindex");
    }

    private static async Task<IResult> SearchDocuments(
        HttpContext context,
        [FromServices] IMeilisearchService searchService,
        [FromQuery] string? q,
        [FromQuery] string? type,
        [FromQuery] string? page,
        [FromQuery] string? size)
    {
        if (string.IsNullOrEmpty(q))
        {
            return Results.Json(new { error = "Query parameter 'q' is required" }, statusCode: 400);
        }

        int pageNum;
        int pageSize;
        try
        {
            pageNum = Math.Max(1, int.Parse(page ?? "1"));
            pageSize = Math.Max(1, Math.Min(100, int.Parse(size ?? "20")));
        }
        catch (Exception ex) when (ex is FormatException or OverflowException)
        {
            return Results.Json(new { error = "Invalid page or size parameter" }, statusCode: 400);
        }

        var ownerId = context.Request.Headers["X-User-ID"].FirstOrDefault()?.Trim();
        if (string.IsNullOrEmpty(ownerId))
        {
            ownerId = null;
        }

        try
        {
            var results = await searchService.SearchAsync(q, type, ownerId, pageNum, pageSize);
            return Results.Json(results);
        }
        catch (ArgumentException ex)
        {
            return Results.Json(new { error = ex.Message }, statusCode: 400);
        }
        catch (Exception)
        {
            return Results.Json(new { error = "Search failed" }, statusCode: 500);
        }
    }

    private static async Task<IResult> Suggest(
        [FromServices] IMeilisearchService searchService,
        [FromQuery] string? q)
    {
        var prefix = q ?? string.Empty;
        if (string.IsNullOrEmpty(prefix) || prefix.Length < 2)
        {
            return Results.Json(new { suggestions = Array.Empty<string>(), query = prefix });
        }

        try
        {
            var suggestions = await searchService.SuggestAsync(prefix);
            return Results.Json(new { suggestions, query = prefix });
        }
        catch (Exception)
        {
            return Results.Json(new { suggestions = Array.Empty<string>(), query = prefix });
        }
    }

    private static async Task<IResult> AdvancedSearch(
        HttpContext context,
        [FromServices] IMeilisearchService searchService,
        [FromBody] AdvancedSearchRequest? request)
    {
        request ??= new AdvancedSearchRequest();

        int pageNum;
        int pageSize;
        try
        {
            pageNum = Math.Max(request.Page ?? 1, 1);
            pageSize = Math.Min(Math.Max(request.Size ?? 20, 1), 100);
        }
        catch (Exception ex) when (ex is FormatException or OverflowException)
        {
            return Results.Json(new { error = "Invalid page or size parameter" }, statusCode: 400);
        }

        var ownerId = context.Request.Headers["X-User-ID"].FirstOrDefault()?.Trim();
        if (string.IsNullOrEmpty(ownerId))
        {
            ownerId = null;
        }

        try
        {
            var results = await searchService.AdvancedSearchAsync(
                request.Query, request.Type, ownerId, request.Tags,
                request.DateFrom, request.DateTo, pageNum, pageSize);
            return Results.Json(results);
        }
        catch (Exception)
        {
            return Results.Json(new { error = "Advanced search failed" }, statusCode: 500);
        }
    }

    private static IResult GetAnalytics([FromServices] IMeilisearchService searchService)
    {
        try
        {
            var analytics = searchService.GetAnalytics();
            return Results.Json(analytics);
        }
        catch (Exception)
        {
            return Results.Json(new { error = "Failed to retrieve analytics" }, statusCode: 500);
        }
    }

    private static async Task<IResult> IndexDocument(
        [FromServices] IIndexer indexer,
        [FromBody] IndexDocumentRequest? request)
    {
        if (request is null)
        {
            return Results.Json(new { error = "Request body is required" }, statusCode: 400);
        }

        try
        {
            var result = await indexer.IndexDocumentAsync(request);
            return Results.Json(result, statusCode: 201);
        }
        catch (ArgumentException ex)
        {
            return Results.Json(new { error = ex.Message }, statusCode: 400);
        }
        catch (Exception)
        {
            return Results.Json(new { error = "Failed to index document" }, statusCode: 500);
        }
    }

    private static async Task<IResult> IndexFile(
        [FromServices] IIndexer indexer,
        [FromBody] IndexFileRequest? request)
    {
        if (request is null)
        {
            return Results.Json(new { error = "Request body is required" }, statusCode: 400);
        }

        try
        {
            var result = await indexer.IndexFileAsync(request);
            return Results.Json(result, statusCode: 201);
        }
        catch (ArgumentException ex)
        {
            return Results.Json(new { error = ex.Message }, statusCode: 400);
        }
        catch (Exception)
        {
            return Results.Json(new { error = "Failed to index file" }, statusCode: 500);
        }
    }

    private static async Task<IResult> RemoveFromIndex(
        [FromServices] IIndexer indexer,
        string docType,
        string docId)
    {
        try
        {
            var result = await indexer.RemoveAsync(docType, docId);
            if (result.Status == "not_found")
            {
                return Results.Json(result, statusCode: 404);
            }

            return Results.Json(result);
        }
        catch (ArgumentException ex)
        {
            return Results.Json(new { error = ex.Message }, statusCode: 400);
        }
        catch (Exception)
        {
            return Results.Json(new { error = "Failed to remove from index" }, statusCode: 500);
        }
    }

    private static async Task<IResult> Reindex([FromServices] IIndexer indexer)
    {
        try
        {
            var result = await indexer.ReindexAsync();
            return Results.Json(result);
        }
        catch (Exception)
        {
            return Results.Json(new { error = "Failed to reindex" }, statusCode: 500);
        }
    }
}
