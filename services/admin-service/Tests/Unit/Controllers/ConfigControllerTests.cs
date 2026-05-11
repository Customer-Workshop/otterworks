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

public class ConfigControllerTests
{
    private readonly AdminDbContext _context;
    private readonly ConfigController _controller;

    public ConfigControllerTests()
    {
        _context = TestDbContext.Create();
        var auditLogger = new AuditLogger(_context, Mock.Of<ILogger<AuditLogger>>());
        _controller = new ConfigController(_context, auditLogger);
        _controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext(),
        };
    }

    [Fact]
    public async Task Index_ReturnsOnlyPublicConfigs()
    {
        CreateConfig("public_key", "value", false);
        CreateConfig("secret_key", "hidden", true);

        var result = await _controller.Index() as OkObjectResult;

        Assert.NotNull(result);
        var response = result.Value as SystemConfigsListResponse;
        Assert.NotNull(response);
        Assert.Single(response.Configs);
        Assert.Equal("public_key", response.Configs[0].Key);
    }

    [Fact]
    public async Task Update_UpdatesConfigValue()
    {
        var config = CreateConfig("update_key", "old_value", false);
        var body = JsonSerializer.Deserialize<JsonElement>("{\"config\":{\"value\":\"new_value\"}}");

        var result = await _controller.Update(config.Id, body) as OkObjectResult;

        Assert.NotNull(result);
        var response = result.Value as SystemConfigResponse;
        Assert.NotNull(response);
        Assert.Equal("new_value", response.Value);
    }

    private SystemConfig CreateConfig(string key, string value, bool isSecret)
    {
        var config = new SystemConfig
        {
            Id = Guid.NewGuid(),
            Key = key,
            Value = value,
            ValueType = "string",
            IsSecret = isSecret,
            CreatedAt = DateTime.UtcNow,
            UpdatedAt = DateTime.UtcNow,
        };
        _context.SystemConfigs.Add(config);
        _context.SaveChanges();
        return config;
    }
}
