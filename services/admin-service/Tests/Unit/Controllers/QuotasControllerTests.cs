using System.Text.Json;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging;
using Moq;
using OtterWorks.AdminService.Controllers;
using OtterWorks.AdminService.Data;
using OtterWorks.AdminService.Models;
using OtterWorks.AdminService.Models.Dto;
using OtterWorks.AdminService.Services;

namespace OtterWorks.AdminService.Tests.Unit.Controllers;

public class QuotasControllerTests
{
    private readonly AdminDbContext _context;
    private readonly QuotasController _controller;

    public QuotasControllerTests()
    {
        _context = TestDbContext.Create();
        var auditLogger = new AuditLogger(_context, Mock.Of<ILogger<AuditLogger>>());
        _controller = new QuotasController(_context, auditLogger);
        _controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext(),
        };
    }

    [Fact]
    public async Task Show_ReturnsStorageQuota()
    {
        var userId = Guid.NewGuid();
        CreateQuota(userId);

        var result = await _controller.Show(userId) as OkObjectResult;

        Assert.NotNull(result);
        var response = result.Value as StorageQuotaResponse;
        Assert.NotNull(response);
        Assert.Equal(userId, response.UserId);
        Assert.Equal("free", response.Tier);
    }

    [Fact]
    public async Task Show_Returns404ForUnknownUser()
    {
        var result = await _controller.Show(Guid.NewGuid()) as NotFoundObjectResult;

        Assert.NotNull(result);
        Assert.Equal(404, result.StatusCode);
    }

    [Fact]
    public async Task Update_UpdatesQuota()
    {
        var userId = Guid.NewGuid();
        CreateQuota(userId);
        var body = JsonSerializer.Deserialize<JsonElement>(
            "{\"quota\":{\"tier\":\"pro\",\"quota_bytes\":214748364800}}");

        var result = await _controller.Update(userId, body) as OkObjectResult;

        Assert.NotNull(result);
        var response = result.Value as StorageQuotaResponse;
        Assert.NotNull(response);
        Assert.Equal("pro", response.Tier);
    }

    [Fact]
    public async Task Update_ReturnsErrorsForInvalidTier()
    {
        var userId = Guid.NewGuid();
        CreateQuota(userId);
        var body = JsonSerializer.Deserialize<JsonElement>(
            "{\"quota\":{\"tier\":\"invalid\"}}");

        var result = await _controller.Update(userId, body) as UnprocessableEntityObjectResult;

        Assert.NotNull(result);
        Assert.Equal(422, result.StatusCode);
    }

    private StorageQuota CreateQuota(Guid userId)
    {
        var quota = new StorageQuota
        {
            Id = Guid.NewGuid(),
            UserId = userId,
            QuotaBytes = 5368709120,
            UsedBytes = 1073741824,
            Tier = "free",
            CreatedAt = DateTime.UtcNow,
            UpdatedAt = DateTime.UtcNow,
        };
        _context.StorageQuotas.Add(quota);
        _context.SaveChanges();
        return quota;
    }
}
