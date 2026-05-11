using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging;
using Moq;
using OtterWorks.AdminService.Controllers;
using OtterWorks.AdminService.Data;
using OtterWorks.AdminService.Models;
using OtterWorks.AdminService.Models.Dto;
using OtterWorks.AdminService.Services;

namespace OtterWorks.AdminService.Tests.Unit.Controllers;

public class MetricsControllerTests
{
    private readonly AdminDbContext _context;
    private readonly MetricsController _controller;

    public MetricsControllerTests()
    {
        _context = TestDbContext.Create();
        var metricsAggregator = new MetricsAggregator(_context);
        _controller = new MetricsController(metricsAggregator);
    }

    [Fact]
    public async Task Summary_ReturnsMetricsSummary()
    {
        CreateTestData();

        var result = await _controller.Summary() as OkObjectResult;

        Assert.NotNull(result);
        var response = result.Value as MetricsSummaryResponse;
        Assert.NotNull(response);
        Assert.NotNull(response.Users);
        Assert.NotNull(response.Storage);
        Assert.NotNull(response.Features);
        Assert.NotNull(response.Announcements);
        Assert.NotNull(response.Audit);
        Assert.Equal(2, response.Users.Total);
        Assert.Equal(1, response.Features.Enabled);
    }

    private void CreateTestData()
    {
        _context.AdminUsers.Add(new AdminUser
        {
            Id = Guid.NewGuid(), Email = "u1@test.com", DisplayName = "U1",
            Role = "viewer", Status = "active", CreatedAt = DateTime.UtcNow, UpdatedAt = DateTime.UtcNow,
        });
        _context.AdminUsers.Add(new AdminUser
        {
            Id = Guid.NewGuid(), Email = "u2@test.com", DisplayName = "U2",
            Role = "admin", Status = "active", CreatedAt = DateTime.UtcNow, UpdatedAt = DateTime.UtcNow,
        });
        _context.FeatureFlags.Add(new FeatureFlag
        {
            Id = Guid.NewGuid(), Name = "test_flag", Enabled = true,
            RolloutPercentage = 100, CreatedAt = DateTime.UtcNow, UpdatedAt = DateTime.UtcNow,
        });
        _context.StorageQuotas.Add(new StorageQuota
        {
            Id = Guid.NewGuid(), UserId = Guid.NewGuid(),
            QuotaBytes = 5368709120, UsedBytes = 1073741824, Tier = "free",
            CreatedAt = DateTime.UtcNow, UpdatedAt = DateTime.UtcNow,
        });
        _context.SaveChanges();
    }
}
