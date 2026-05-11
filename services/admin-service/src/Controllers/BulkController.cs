using System.Text.Json;
using Microsoft.AspNetCore.Mvc;
using OtterWorks.AdminService.Models.Dto;
using OtterWorks.AdminService.Services;

namespace OtterWorks.AdminService.Controllers;

[ApiController]
[Route("api/v1/admin/bulk")]
public class BulkController : ControllerBase
{
    private readonly IBulkOperationsService _bulkService;

    public BulkController(IBulkOperationsService bulkService)
    {
        _bulkService = bulkService;
    }

    [HttpPost("users")]
    public async Task<IActionResult> Users([FromBody] JsonElement body)
    {
        if (!body.TryGetProperty("operation", out var operationProp))
        {
            return BadRequest(new { error = "Missing parameter: operation" });
        }

        if (!body.TryGetProperty("user_ids", out var userIdsProp) || userIdsProp.ValueKind != JsonValueKind.Array)
        {
            return BadRequest(new { error = "user_ids must be a non-empty array" });
        }

        var userIds = new List<Guid>();
        foreach (var item in userIdsProp.EnumerateArray())
        {
            if (Guid.TryParse(item.GetString(), out var id))
            {
                userIds.Add(id);
            }
        }

        if (userIds.Count == 0)
        {
            return BadRequest(new { error = "user_ids must be a non-empty array" });
        }

        var operation = operationProp.GetString() ?? string.Empty;
        string? reason = body.TryGetProperty("reason", out var reasonProp) ? reasonProp.GetString() : null;
        string? role = body.TryGetProperty("role", out var roleProp) ? roleProp.GetString() : null;

        var result = await _bulkService.ProcessAsync(operation, userIds, reason, role);

        var response = new BulkUsersResponse
        {
            Operation = operation,
            SuccessCount = result.SuccessCount,
            FailureCount = result.FailureCount,
            Errors = result.Errors,
        };

        var statusCode = GetStatusCode(result);
        return StatusCode(statusCode, response);
    }

    private static int GetStatusCode(BulkResult result)
    {
        if (result.Errors.Count > 0 && result.SuccessCount == 0 && result.FailureCount == 0)
        {
            return 400;
        }

        if (result.SuccessCount == 0 && result.FailureCount > 0)
        {
            return 422;
        }

        if (result.FailureCount == 0)
        {
            return 200;
        }

        return 207;
    }
}
