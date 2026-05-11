using OtterWorks.AdminService.Models;

namespace OtterWorks.AdminService.Tests.Unit.Models;

public class StorageQuotaTests
{
    [Fact]
    public void UsagePercentage_CalculatesCorrectly()
    {
        var quota = new StorageQuota { QuotaBytes = 5368709120, UsedBytes = 1073741824 };

        Assert.Equal(20.0, quota.UsagePercentage);
    }

    [Fact]
    public void UsagePercentage_ReturnsZeroWhenQuotaIsZero()
    {
        var quota = new StorageQuota { QuotaBytes = 0, UsedBytes = 0 };

        Assert.Equal(0, quota.UsagePercentage);
    }

    [Fact]
    public void OverQuota_ReturnsTrueWhenUsedExceedsQuota()
    {
        var quota = new StorageQuota { QuotaBytes = 5368709120, UsedBytes = 6000000000 };

        Assert.True(quota.OverQuota);
    }

    [Fact]
    public void OverQuota_ReturnsFalseWhenUnderQuota()
    {
        var quota = new StorageQuota { QuotaBytes = 5368709120, UsedBytes = 1073741824 };

        Assert.False(quota.OverQuota);
    }

    [Fact]
    public void RemainingBytes_CalculatesCorrectly()
    {
        var quota = new StorageQuota { QuotaBytes = 5368709120, UsedBytes = 1073741824 };

        Assert.Equal(5368709120 - 1073741824, quota.RemainingBytes);
    }

    [Fact]
    public void RemainingBytes_ReturnsZeroWhenOverQuota()
    {
        var quota = new StorageQuota { QuotaBytes = 5368709120, UsedBytes = 6000000000 };

        Assert.Equal(0, quota.RemainingBytes);
    }

    [Fact]
    public void ValidTiers_ContainsExpectedValues()
    {
        Assert.Contains("free", StorageQuota.ValidTiers);
        Assert.Contains("basic", StorageQuota.ValidTiers);
        Assert.Contains("pro", StorageQuota.ValidTiers);
        Assert.Contains("enterprise", StorageQuota.ValidTiers);
    }
}
