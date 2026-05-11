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

public class FeaturesControllerTests
{
    private readonly AdminDbContext _context;
    private readonly FeaturesController _controller;

    public FeaturesControllerTests()
    {
        _context = TestDbContext.Create();
        var auditLogger = new AuditLogger(_context, Mock.Of<ILogger<AuditLogger>>());
        _controller = new FeaturesController(_context, auditLogger);
        _controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext(),
        };
    }

    [Fact]
    public async Task Index_ReturnsAllFeatureFlags()
    {
        CreateFlag("feature_a", true);
        CreateFlag("feature_b", false);

        var result = await _controller.Index(null) as OkObjectResult;

        Assert.NotNull(result);
        var response = result.Value as FeatureFlagsListResponse;
        Assert.NotNull(response);
        Assert.Equal(2, response.Features.Count);
    }

    [Fact]
    public async Task Index_FiltersByEnabledStatus()
    {
        CreateFlag("enabled_flag", true);
        CreateFlag("disabled_flag", false);

        var result = await _controller.Index("true") as OkObjectResult;

        Assert.NotNull(result);
        var response = result.Value as FeatureFlagsListResponse;
        Assert.NotNull(response);
        Assert.All(response.Features, f => Assert.True(f.Enabled));
    }

    [Fact]
    public async Task Show_ReturnsFeatureFlag()
    {
        var flag = CreateFlag("show_flag", false);

        var result = await _controller.Show(flag.Id) as OkObjectResult;

        Assert.NotNull(result);
        var response = result.Value as FeatureFlagResponse;
        Assert.NotNull(response);
        Assert.Equal(flag.Name, response.Name);
    }

    [Fact]
    public async Task Create_CreatesNewFeatureFlag()
    {
        var body = JsonSerializer.Deserialize<JsonElement>(
            "{\"feature\":{\"name\":\"new_feature\",\"description\":\"A new feature\",\"enabled\":true,\"rollout_percentage\":50}}");

        var result = await _controller.Create(body) as ObjectResult;

        Assert.NotNull(result);
        Assert.Equal(201, result.StatusCode);
        Assert.Equal(1, _context.FeatureFlags.Count());
    }

    [Fact]
    public async Task Create_ReturnsErrorsForInvalidParams()
    {
        var body = JsonSerializer.Deserialize<JsonElement>(
            "{\"feature\":{\"name\":\"Invalid Name\"}}");

        var result = await _controller.Create(body) as UnprocessableEntityObjectResult;

        Assert.NotNull(result);
        Assert.Equal(422, result.StatusCode);
    }

    [Fact]
    public async Task Update_UpdatesFeatureFlag()
    {
        var flag = CreateFlag("update_flag", false);
        var body = JsonSerializer.Deserialize<JsonElement>(
            "{\"feature\":{\"enabled\":true}}");

        var result = await _controller.Update(flag.Id, body) as OkObjectResult;

        Assert.NotNull(result);
        var response = result.Value as FeatureFlagResponse;
        Assert.NotNull(response);
        Assert.True(response.Enabled);
    }

    [Fact]
    public async Task Destroy_DeletesFeatureFlag()
    {
        var flag = CreateFlag("delete_flag", false);

        var result = await _controller.Destroy(flag.Id) as NoContentResult;

        Assert.NotNull(result);
        Assert.Equal(0, _context.FeatureFlags.Count());
    }

    private FeatureFlag CreateFlag(string name, bool enabled)
    {
        var flag = new FeatureFlag
        {
            Id = Guid.NewGuid(),
            Name = name,
            Description = "Test flag",
            Enabled = enabled,
            RolloutPercentage = enabled ? 100 : 0,
            CreatedAt = DateTime.UtcNow,
            UpdatedAt = DateTime.UtcNow,
        };
        _context.FeatureFlags.Add(flag);
        _context.SaveChanges();
        return flag;
    }
}
