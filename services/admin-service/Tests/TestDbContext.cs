using Microsoft.EntityFrameworkCore;
using OtterWorks.AdminService.Data;

namespace OtterWorks.AdminService.Tests;

public static class TestDbContext
{
    public static AdminDbContext Create()
    {
        var options = new DbContextOptionsBuilder<AdminDbContext>()
            .UseInMemoryDatabase(databaseName: Guid.NewGuid().ToString())
            .Options;

        var context = new AdminDbContext(options);
        context.Database.EnsureCreated();
        return context;
    }
}
