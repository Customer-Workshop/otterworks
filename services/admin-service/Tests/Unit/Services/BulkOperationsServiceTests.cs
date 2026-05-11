using Microsoft.Extensions.Logging;
using Moq;
using OtterWorks.AdminService.Data;
using OtterWorks.AdminService.Models;
using OtterWorks.AdminService.Services;

namespace OtterWorks.AdminService.Tests.Unit.Services;

public class BulkOperationsServiceTests
{
    private readonly AdminDbContext _context;
    private readonly BulkOperationsService _service;

    public BulkOperationsServiceTests()
    {
        _context = TestDbContext.Create();
        var auditLogger = new AuditLogger(_context, Mock.Of<ILogger<AuditLogger>>());
        _service = new BulkOperationsService(_context, auditLogger);
    }

    [Fact]
    public async Task Process_SuspendsUsersInBulk()
    {
        var users = CreateUsers(3);
        var userIds = users.Select(u => u.Id).ToList();

        var result = await _service.ProcessAsync("suspend", userIds);

        Assert.Equal(3, result.SuccessCount);
        Assert.Equal(0, result.FailureCount);
        Assert.All(users, u => Assert.Equal("suspended", _context.AdminUsers.Find(u.Id)!.Status));
    }

    [Fact]
    public async Task Process_ActivatesUsersInBulk()
    {
        var users = CreateUsers(3);
        foreach (var u in users)
        {
            u.Suspend();
        }

        await _context.SaveChangesAsync();
        var userIds = users.Select(u => u.Id).ToList();

        var result = await _service.ProcessAsync("activate", userIds);

        Assert.Equal(3, result.SuccessCount);
        Assert.All(users, u => Assert.Equal("active", _context.AdminUsers.Find(u.Id)!.Status));
    }

    [Fact]
    public async Task Process_SoftDeletesUsersInBulk()
    {
        var users = CreateUsers(3);
        var userIds = users.Select(u => u.Id).ToList();

        var result = await _service.ProcessAsync("delete", userIds);

        Assert.Equal(3, result.SuccessCount);
        Assert.All(users, u => Assert.Equal("deleted", _context.AdminUsers.Find(u.Id)!.Status));
    }

    [Fact]
    public async Task Process_UpdatesRolesInBulk()
    {
        var users = CreateUsers(3);
        var userIds = users.Select(u => u.Id).ToList();

        var result = await _service.ProcessAsync("update_role", userIds, role: "editor");

        Assert.Equal(3, result.SuccessCount);
        Assert.All(users, u => Assert.Equal("editor", _context.AdminUsers.Find(u.Id)!.Role));
    }

    [Fact]
    public async Task Process_ReturnsErrorForInvalidOperation()
    {
        var users = CreateUsers(1);
        var userIds = users.Select(u => u.Id).ToList();

        var result = await _service.ProcessAsync("invalid", userIds);

        Assert.Contains(result.Errors, e => e.ToString()!.Contains("Invalid operation: invalid"));
    }

    [Fact]
    public async Task Process_ReportsMissingUsers()
    {
        var users = CreateUsers(3);
        var userIds = users.Select(u => u.Id).ToList();
        userIds.Add(Guid.NewGuid());

        var result = await _service.ProcessAsync("suspend", userIds);

        Assert.Equal(3, result.SuccessCount);
        Assert.Equal(1, result.FailureCount);
    }

    private List<AdminUser> CreateUsers(int count)
    {
        var users = new List<AdminUser>();
        for (int i = 0; i < count; i++)
        {
            var user = new AdminUser
            {
                Id = Guid.NewGuid(),
                Email = $"user{i}@test.com",
                DisplayName = $"User {i}",
                Role = "viewer",
                Status = "active",
                CreatedAt = DateTime.UtcNow,
                UpdatedAt = DateTime.UtcNow,
            };
            users.Add(user);
            _context.AdminUsers.Add(user);
        }

        _context.SaveChanges();
        return users;
    }
}
