using System.Text.Json;
using Microsoft.AspNetCore.Mvc;
using OtterWorks.SearchService.Services;
namespace OtterWorks.SearchService.Controllers;

[ApiController]
[Route("api/v1/search")]
public class IndexController : ControllerBase
{
    private readonly IIndexerService _indexer;
    private readonly Serilog.ILogger _logger = Serilog.Log.ForContext<IndexController>();

    public IndexController(IIndexerService indexer)
    {
        _indexer = indexer;
    }

    [HttpPost("index/document")]
    public IActionResult IndexDocument()
    {
        Dictionary<string, object?>? data;
        try
        {
            using var reader = new StreamReader(Request.Body);
            var body = reader.ReadToEndAsync().GetAwaiter().GetResult();
            if (string.IsNullOrWhiteSpace(body))
                return BadRequest(new { error = "Request body is required" });
            data = JsonSerializer.Deserialize<Dictionary<string, object?>>(body);
        }
        catch
        {
            return BadRequest(new { error = "Request body is required" });
        }

        if (data is null)
            return BadRequest(new { error = "Request body is required" });

        try
        {
            var result = _indexer.IndexDocument(data);
            _logger.Information("API document indexed: {DocumentId}", data.GetValueOrDefault("id"));
            return StatusCode(201, result);
        }
        catch (ArgumentException e)
        {
            return BadRequest(new { error = e.Message });
        }
        catch (Exception ex)
        {
            _logger.Error(ex, "API index document failed");
            return StatusCode(500, new { error = "Failed to index document" });
        }
    }

    [HttpPost("index/file")]
    public IActionResult IndexFile()
    {
        Dictionary<string, object?>? data;
        try
        {
            using var reader = new StreamReader(Request.Body);
            var body = reader.ReadToEndAsync().GetAwaiter().GetResult();
            if (string.IsNullOrWhiteSpace(body))
                return BadRequest(new { error = "Request body is required" });
            data = JsonSerializer.Deserialize<Dictionary<string, object?>>(body);
        }
        catch
        {
            return BadRequest(new { error = "Request body is required" });
        }

        if (data is null)
            return BadRequest(new { error = "Request body is required" });

        try
        {
            var result = _indexer.IndexFile(data);
            _logger.Information("API file indexed: {FileId}", data.GetValueOrDefault("id"));
            return StatusCode(201, result);
        }
        catch (ArgumentException e)
        {
            return BadRequest(new { error = e.Message });
        }
        catch (Exception ex)
        {
            _logger.Error(ex, "API index file failed");
            return StatusCode(500, new { error = "Failed to index file" });
        }
    }

    [HttpDelete("index/{docType}/{docId}")]
    public IActionResult RemoveFromIndex(string docType, string docId)
    {
        try
        {
            var result = _indexer.Remove(docType, docId);
            if (result["status"]?.ToString() == "not_found")
                return NotFound(result);

            _logger.Information("API document removed: {DocType}/{DocId}", docType, docId);
            return Ok(result);
        }
        catch (ArgumentException e)
        {
            return BadRequest(new { error = e.Message });
        }
        catch (Exception ex)
        {
            _logger.Error(ex, "API remove from index failed");
            return StatusCode(500, new { error = "Failed to remove from index" });
        }
    }

    [HttpPost("reindex")]
    public IActionResult ReindexAll()
    {
        try
        {
            var result = _indexer.Reindex();
            _logger.Information("API reindex triggered");
            return Ok(result);
        }
        catch (Exception ex)
        {
            _logger.Error(ex, "API reindex failed");
            return StatusCode(500, new { error = "Failed to reindex" });
        }
    }
}
