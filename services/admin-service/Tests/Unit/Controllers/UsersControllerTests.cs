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

public class UsersControllerTests
{
    private readonly AdminDbContext _context;
    private readonly UsersController _controller;

    public UsersControllerTests()
    {
        _context = TestDbContext.Create();
        var auditLogger = new AuditLogger(_context, Mock.Of<ILogger<AuditLogger>>());
        _controller = new UsersController(_context, auditLogger);
        _controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext(),
        };
    }

    [Fact]
    public async Task Index_ReturnsPaginatedUserList()
    {
        CreateUsers(3);

        var result = await _controller.Index(null, null, null) as OkObjectResult;

        Assert.NotNull(result);
        var response = result.Value as AdminUsersListResponse;
        Assert.NotNull(response);
        Assert.Equal(3, response.Users.Count);
        Assert.Equal(3, response.Total);
    }

    [Fact]
    public async Task Index_FiltersByRole()
    {
        CreateUsers(2);
        CreateUser("admin@test.com", "Admin User", "admin");

        var result = await _controller.Index(null, "admin", null) as OkObjectResult;

        Assert.NotNull(result);
        var response = result.Value as AdminUsersListResponse;
        Assert.NotNull(response);
        Assert.All(response.Users, u => Assert.Equal("admin", u.Role));
    }

    [Fact]
    public async Task Index_FiltersByStatus()
    {
        CreateUsers(2);
        var suspended = CreateUser("sus@test.com", "Suspended", "viewer");
        suspended.Suspend("Test");
        _context.SaveChanges();

        var result = await _controller.Index(null, null, "suspended") as OkObjectResult;

        Assert.NotNull(result);
        var response = result.Value as AdminUsersListResponse;
        Assert.NotNull(response);
        Assert.All(response.Users, u => Assert.Equal("suspended", u.Status));
    }

    [Fact]
    public async Task Show_ReturnsUserDetails()
    {
        var user = CreateUser("show@test.com", "Show User", "viewer");

        var result = await _controller.Show(user.Id) as OkObjectResult;

        Assert.NotNull(result);
        var response = result.Value as AdminUserResponse;
        Assert.NotNull(response);
        Assert.Equal(user.Id, response.Id);
        Assert.Equal(user.Email, response.Email);
    }

    [Fact]
    public async Task Show_Returns404ForMissingUser()
    {
        var result = await _controller.Show(Guid.NewGuid()) as NotFoundObjectResult;

        Assert.NotNull(result);
        Assert.Equal(404, result.StatusCode);
    }

    [Fact]
    public async Task Update_UpdatesUserAttributes()
    {
        var user = CreateUser("update@test.com", "Old Name", "viewer");
        var body = JsonSerializer.Deserialize<JsonElement>("{\"user\":{\"display_name\":\"New Name\"}}");

        var result = await _controller.Update(user.Id, body) as OkObjectResult;

        Assert.NotNull(result);
        var response = result.Value as AdminUserResponse;
        Assert.NotNull(response);
        Assert.Equal("New Name", response.DisplayName);
    }

    [Fact]
    public async Task Update_ReturnsErrorsForInvalidParams()
    {
        var user = CreateUser("invalid@test.com", "User", "viewer");
        var body = JsonSerializer.Deserialize<JsonElement>("{\"user\":{\"role\":\"invalid_role\"}}");

        var result = await _controller.Update(user.Id, body) as UnprocessableEntityObjectResult;

        Assert.NotNull(result);
        Assert.Equal(422, result.StatusCode);
    }

    [Fact]
    public async Task Destroy_SoftDeletesUser()
    {
        var user = CreateUser("delete@test.com", "Delete User", "viewer");

        var result = await _controller.Destroy(user.Id) as NoContentResult;

        Assert.NotNull(result);
        var deleted = _context.AdminUsers.Find(user.Id);
        Assert.Equal("deleted", deleted!.Status);
    }

    [Fact]
    public async Task Suspend_SuspendsUser()
    {
        var user = CreateUser("suspend@test.com", "Suspend User", "viewer");
        var body = JsonSerializer.Deserialize<JsonElement>("{\"reason\":\"Policy violation\"}");

        var result = await _controller.Suspend(user.Id, body) as OkObjectResult;

        Assert.NotNull(result);
        var response = result.Value as AdminUserResponse;
        Assert.NotNull(response);
        Assert.Equal("suspended", response.Status);
    }

    [Fact]
    public async Task Activate_ActivatesUser()
    {
        var user = CreateUser("activate@test.com", "Activate User", "viewer");
        user.Suspend("Test");
        _context.SaveChanges();

        var result = await _controller.Activate(user.Id) as OkObjectResult;

        Assert.NotNull(result);
        var response = result.Value as AdminUserResponse;
        Assert.NotNull(response);
        Assert.Equal("active", response.Status);
    }

    private AdminUser CreateUser(string email, string name, string role)
    {
        var user = new AdminUser
        {
            Id = Guid.NewGuid(),
            Email = email,
            DisplayName = name,
            Role = role,
            Status = "active",
            CreatedAt = DateTime.UtcNow,
            UpdatedAt = DateTime.UtcNow,
        };
        _context.AdminUsers.Add(user);
        _context.SaveChanges();
        return user;
    }

    private void CreateUsers(int count)
    {
        for (int i = 0; i < count; i++)
        {
            CreateUser($"user{i}_{Guid.NewGuid():N}@test.com", $"User {i}", "viewer");
        }
    }
}
