using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using OtterWorks.AdminService.Controllers;
using OtterWorks.AdminService.Data;
using OtterWorks.AdminService.Models;
using OtterWorks.AdminService.Models.Dto;

namespace OtterWorks.AdminService.Tests.Unit.Controllers;

public class AuditLogsControllerTests
{
    private readonly AdminDbContext _context;
    private readonly AuditLogsController _controller;

    public AuditLogsControllerTests()
    {
        _context = TestDbContext.Create();
        _controller = new AuditLogsController(_context);
        _controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext(),
        };
    }

    [Fact]
    public async Task Index_ReturnsPaginatedAuditLogs()
    {
        CreateLogs(3);

        var result = await _controller.Index(null, null, null, null, null, null) as OkObjectResult;

        Assert.NotNull(result);
        var response = result.Value as AuditLogsListResponse;
        Assert.NotNull(response);
        Assert.Equal(3, response.AuditLogs.Count);
    }

    [Fact]
    public async Task Index_FiltersByActionType()
    {
        CreateLog("user.updated", "AdminUser");
        CreateLog("feature_flag.created", "FeatureFlag");

        var result = await _controller.Index("feature_flag.created", null, null, null, null, null) as OkObjectResult;

        Assert.NotNull(result);
        var response = result.Value as AuditLogsListResponse;
        Assert.NotNull(response);
        Assert.All(response.AuditLogs, l => Assert.Equal("feature_flag.created", l.Action));
    }

    [Fact]
    public async Task Index_FiltersByResourceType()
    {
        CreateLog("user.updated", "AdminUser");
        CreateLog("feature_flag.created", "FeatureFlag");

        var result = await _controller.Index(null, "AdminUser", null, null, null, null) as OkObjectResult;

        Assert.NotNull(result);
        var response = result.Value as AuditLogsListResponse;
        Assert.NotNull(response);
        Assert.All(response.AuditLogs, l => Assert.Equal("AdminUser", l.ResourceType));
    }

    [Fact]
    public async Task Show_ReturnsAuditLogEntry()
    {
        var log = CreateLog("user.updated", "AdminUser");

        var result = await _controller.Show(log.Id) as OkObjectResult;

        Assert.NotNull(result);
        var response = result.Value as AuditLogResponse;
        Assert.NotNull(response);
        Assert.Equal(log.Id, response.Id);
    }

    private void CreateLogs(int count)
    {
        for (int i = 0; i < count; i++)
        {
            CreateLog("user.updated", "AdminUser");
        }
    }

    private AuditLog CreateLog(string action, string resourceType)
    {
        var log = new AuditLog
        {
            Id = Guid.NewGuid(),
            ActorId = Guid.NewGuid(),
            ActorEmail = "actor@test.com",
            Action = action,
            ResourceType = resourceType,
            ResourceId = Guid.NewGuid(),
            ChangesMade = "{\"role\":\"admin\"}",
            IpAddress = "127.0.0.1",
            UserAgent = "Test Agent",
            CreatedAt = DateTime.UtcNow,
            UpdatedAt = DateTime.UtcNow,
        };
        _context.AuditLogs.Add(log);
        _context.SaveChanges();
        return log;
    }
}
