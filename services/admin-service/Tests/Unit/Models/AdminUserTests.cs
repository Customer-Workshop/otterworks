using OtterWorks.AdminService.Models;

namespace OtterWorks.AdminService.Tests.Unit.Models;

public class AdminUserTests
{
    [Fact]
    public void Suspend_SetsStatusAndTimestamp()
    {
        var user = new AdminUser { Id = Guid.NewGuid(), Email = "test@test.com", DisplayName = "Test", Status = "active" };

        user.Suspend("Violation");

        Assert.Equal("suspended", user.Status);
        Assert.NotNull(user.SuspendedAt);
        Assert.Equal("Violation", user.SuspendedReason);
    }

    [Fact]
    public void Activate_ClearsSuspension()
    {
        var user = new AdminUser
        {
            Id = Guid.NewGuid(),
            Email = "test@test.com",
            DisplayName = "Test",
            Status = "suspended",
            SuspendedAt = DateTime.UtcNow,
            SuspendedReason = "Violation",
        };

        user.Activate();

        Assert.Equal("active", user.Status);
        Assert.Null(user.SuspendedAt);
        Assert.Null(user.SuspendedReason);
    }

    [Fact]
    public void SoftDelete_MarksAsDeleted()
    {
        var user = new AdminUser { Id = Guid.NewGuid(), Email = "test@test.com", DisplayName = "Test", Status = "active" };

        user.SoftDelete();

        Assert.Equal("deleted", user.Status);
    }

    [Fact]
    public void ValidRoles_ContainsExpectedValues()
    {
        Assert.Contains("super_admin", AdminUser.ValidRoles);
        Assert.Contains("admin", AdminUser.ValidRoles);
        Assert.Contains("editor", AdminUser.ValidRoles);
        Assert.Contains("viewer", AdminUser.ValidRoles);
    }

    [Fact]
    public void ValidStatuses_ContainsExpectedValues()
    {
        Assert.Contains("active", AdminUser.ValidStatuses);
        Assert.Contains("suspended", AdminUser.ValidStatuses);
        Assert.Contains("deleted", AdminUser.ValidStatuses);
    }
}
