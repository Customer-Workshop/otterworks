using Microsoft.EntityFrameworkCore;
using OtterWorks.AdminService.Models;

namespace OtterWorks.AdminService.Data;

public class AdminDbContext : DbContext
{
    public AdminDbContext(DbContextOptions<AdminDbContext> options)
        : base(options)
    {
    }

    public DbSet<AdminUser> AdminUsers { get; set; } = null!;
    public DbSet<FeatureFlag> FeatureFlags { get; set; } = null!;
    public DbSet<SystemConfig> SystemConfigs { get; set; } = null!;
    public DbSet<Announcement> Announcements { get; set; } = null!;
    public DbSet<AuditLog> AuditLogs { get; set; } = null!;
    public DbSet<StorageQuota> StorageQuotas { get; set; } = null!;

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);

        modelBuilder.HasPostgresExtension("pgcrypto");
        modelBuilder.HasPostgresExtension("plpgsql");

        modelBuilder.Entity<AdminUser>(entity =>
        {
            entity.Property(e => e.Id).HasDefaultValueSql("gen_random_uuid()");
            entity.HasIndex(e => e.Email).IsUnique();
            entity.HasIndex(e => e.Role);
            entity.HasIndex(e => e.Status);
            entity.HasOne(e => e.StorageQuota)
                .WithOne()
                .HasForeignKey<StorageQuota>(e => e.UserId)
                .HasPrincipalKey<AdminUser>(e => e.Id);
        });

        modelBuilder.Entity<FeatureFlag>(entity =>
        {
            entity.Property(e => e.Id).HasDefaultValueSql("gen_random_uuid()");
            entity.HasIndex(e => e.Name).IsUnique();
            entity.HasIndex(e => e.Enabled);
        });

        modelBuilder.Entity<SystemConfig>(entity =>
        {
            entity.Property(e => e.Id).HasDefaultValueSql("gen_random_uuid()");
            entity.HasIndex(e => e.Key).IsUnique();
        });

        modelBuilder.Entity<Announcement>(entity =>
        {
            entity.Property(e => e.Id).HasDefaultValueSql("gen_random_uuid()");
            entity.HasIndex(e => e.Severity);
            entity.HasIndex(e => e.Status);
            entity.HasIndex(e => new { e.StartsAt, e.EndsAt });
        });

        modelBuilder.Entity<AuditLog>(entity =>
        {
            entity.Property(e => e.Id).HasDefaultValueSql("gen_random_uuid()");
            entity.HasIndex(e => e.Action);
            entity.HasIndex(e => e.ActorId);
            entity.HasIndex(e => e.CreatedAt);
            entity.HasIndex(e => new { e.ResourceType, e.ResourceId });
        });

        modelBuilder.Entity<StorageQuota>(entity =>
        {
            entity.Property(e => e.Id).HasDefaultValueSql("gen_random_uuid()");
            entity.HasIndex(e => e.UserId).IsUnique();
            entity.HasIndex(e => e.Tier);
        });
    }
}
