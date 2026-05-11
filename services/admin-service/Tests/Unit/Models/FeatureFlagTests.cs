using OtterWorks.AdminService.Models;

namespace OtterWorks.AdminService.Tests.Unit.Models;

public class FeatureFlagTests
{
    [Fact]
    public void Expired_ReturnsTrueWhenPastExpiration()
    {
        var flag = new FeatureFlag { ExpiresAt = DateTime.UtcNow.AddDays(-1) };

        Assert.True(flag.Expired);
    }

    [Fact]
    public void Expired_ReturnsFalseWhenNoExpiration()
    {
        var flag = new FeatureFlag { ExpiresAt = null };

        Assert.False(flag.Expired);
    }

    [Fact]
    public void Expired_ReturnsFalseWhenFutureExpiration()
    {
        var flag = new FeatureFlag { ExpiresAt = DateTime.UtcNow.AddDays(1) };

        Assert.False(flag.Expired);
    }
}
