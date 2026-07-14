using System.Text.Json;
using OtterWorks.AuditService.Models;

namespace AuditService.Tests;

public class ApiErrorResponseTests
{
    [Fact]
    public void SerializesStandardErrorShape()
    {
        var response = ApiErrorResponse.Create("NOT_FOUND", "Event not found.", 404);
        var json = JsonSerializer.Serialize(
            response,
            new JsonSerializerOptions(JsonSerializerDefaults.Web));

        Assert.Equal(
            """{"error":{"code":"NOT_FOUND","message":"Event not found.","status":404}}""",
            json);
    }
}
