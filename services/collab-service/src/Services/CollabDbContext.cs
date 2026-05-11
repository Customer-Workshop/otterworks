using Microsoft.EntityFrameworkCore;
using OtterWorks.CollabService.Models;

namespace OtterWorks.CollabService.Services;

public class CollabDbContext : DbContext
{
    public CollabDbContext(DbContextOptions<CollabDbContext> options)
        : base(options)
    {
    }

    public DbSet<CollaborationSession> Sessions { get; set; } = null!;

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<CollaborationSession>(entity =>
        {
            entity.ToTable("collaboration_sessions");
            entity.HasKey(e => e.Id);
            entity.Property(e => e.DocumentId).IsRequired().HasMaxLength(255);
            entity.Property(e => e.UserId).IsRequired().HasMaxLength(255);
            entity.Property(e => e.DisplayName).HasMaxLength(255);
            entity.HasIndex(e => e.DocumentId);
            entity.HasIndex(e => e.UserId);
            entity.HasIndex(e => e.IsActive);
        });
    }
}
