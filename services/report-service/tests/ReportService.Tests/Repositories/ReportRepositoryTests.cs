using FluentAssertions;
using Microsoft.EntityFrameworkCore;
using OtterWorks.ReportService.Data;
using OtterWorks.ReportService.Models;
using OtterWorks.ReportService.Repositories;

namespace ReportService.Tests.Repositories;

public class ReportRepositoryTests : IDisposable
{
    private readonly ReportDbContext _context;
    private readonly ReportRepository _repository;

    public ReportRepositoryTests()
    {
        var options = new DbContextOptionsBuilder<ReportDbContext>()
            .UseInMemoryDatabase(databaseName: Guid.NewGuid().ToString())
            .Options;
        _context = new ReportDbContext(options);
        _repository = new ReportRepository(_context);
    }

    public void Dispose()
    {
        _context.Dispose();
    }

    private static Report CreateReport(string name = "Test Report", string user = "user-001",
        ReportStatus status = ReportStatus.PENDING)
    {
        return new Report
        {
            ReportName = name,
            Category = ReportCategory.USAGE_ANALYTICS,
            ReportType = ReportType.PDF,
            Status = status,
            RequestedBy = user,
            CreatedAt = DateTime.UtcNow,
            DateFrom = DateTime.UtcNow.AddDays(-30),
            DateTo = DateTime.UtcNow
        };
    }

    [Fact]
    public async Task CreateAsync_ShouldSaveAndReturnReport()
    {
        var report = CreateReport();
        var result = await _repository.CreateAsync(report);

        result.Id.Should().BeGreaterThan(0);
        result.ReportName.Should().Be("Test Report");

        var fetched = await _repository.GetByIdAsync(result.Id);
        fetched.Should().NotBeNull();
        fetched!.ReportName.Should().Be("Test Report");
    }

    [Fact]
    public async Task GetByIdAsync_ShouldReturnNullForNonexistent()
    {
        var result = await _repository.GetByIdAsync(99999);
        result.Should().BeNull();
    }

    [Fact]
    public async Task GetByUserAsync_ShouldReturnOrderedResults()
    {
        var report1 = CreateReport("Report 1", "user-A");
        report1.CreatedAt = DateTime.UtcNow.AddHours(-2);
        await _repository.CreateAsync(report1);

        var report2 = CreateReport("Report 2", "user-A");
        report2.CreatedAt = DateTime.UtcNow.AddHours(-1);
        await _repository.CreateAsync(report2);

        var report3 = CreateReport("Report 3", "user-B");
        await _repository.CreateAsync(report3);

        var results = await _repository.GetByUserAsync("user-A");
        results.Should().HaveCount(2);
        results[0].ReportName.Should().Be("Report 2");
        results[1].ReportName.Should().Be("Report 1");
    }

    [Fact]
    public async Task GetByStatusAsync_ShouldReturnOrderedResults()
    {
        var report1 = CreateReport("Report 1");
        report1.Status = ReportStatus.COMPLETED;
        report1.CreatedAt = DateTime.UtcNow.AddHours(-2);
        await _repository.CreateAsync(report1);

        var report2 = CreateReport("Report 2");
        report2.Status = ReportStatus.COMPLETED;
        report2.CreatedAt = DateTime.UtcNow.AddHours(-1);
        await _repository.CreateAsync(report2);

        var report3 = CreateReport("Report 3");
        report3.Status = ReportStatus.PENDING;
        await _repository.CreateAsync(report3);

        var results = await _repository.GetByStatusAsync(ReportStatus.COMPLETED);
        results.Should().HaveCount(2);
        results[0].ReportName.Should().Be("Report 1");
        results[1].ReportName.Should().Be("Report 2");
    }

    [Fact]
    public async Task DeleteAsync_ShouldReturnTrueForExisting()
    {
        var report = CreateReport();
        await _repository.CreateAsync(report);

        var deleted = await _repository.DeleteAsync(report.Id);
        deleted.Should().BeTrue();

        var fetched = await _repository.GetByIdAsync(report.Id);
        fetched.Should().BeNull();
    }

    [Fact]
    public async Task DeleteAsync_ShouldReturnFalseForNonexistent()
    {
        var deleted = await _repository.DeleteAsync(99999);
        deleted.Should().BeFalse();
    }

    [Fact]
    public async Task UpdateAsync_ShouldPersistChanges()
    {
        var report = CreateReport();
        await _repository.CreateAsync(report);

        report.Status = ReportStatus.COMPLETED;
        report.CompletedAt = DateTime.UtcNow;
        await _repository.UpdateAsync(report);

        var fetched = await _repository.GetByIdAsync(report.Id);
        fetched!.Status.Should().Be(ReportStatus.COMPLETED);
        fetched.CompletedAt.Should().NotBeNull();
    }
}
