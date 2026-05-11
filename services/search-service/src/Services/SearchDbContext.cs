using Microsoft.EntityFrameworkCore;
using OtterWorks.SearchService.Models;

namespace OtterWorks.SearchService.Services;

public class SearchDbContext : DbContext
{
    public SearchDbContext(DbContextOptions<SearchDbContext> options)
        : base(options)
    {
    }

    public DbSet<SearchMetadata> SearchMetadata => Set<SearchMetadata>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<SearchMetadata>(entity =>
        {
            entity.HasIndex(e => e.Key).IsUnique();
        });
    }
}
