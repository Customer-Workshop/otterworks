using Microsoft.EntityFrameworkCore;
using OtterWorks.DocumentService.Models;

namespace OtterWorks.DocumentService.Data;

public class DocumentDbContext : DbContext
{
    public DocumentDbContext(DbContextOptions<DocumentDbContext> options)
        : base(options)
    {
    }

    public DbSet<Document> Documents => Set<Document>();

    public DbSet<DocumentVersion> DocumentVersions => Set<DocumentVersion>();

    public DbSet<Comment> Comments => Set<Comment>();

    public DbSet<Template> Templates => Set<Template>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);

        modelBuilder.Entity<Document>(entity =>
        {
            entity.HasIndex(e => e.OwnerId);
            entity.HasMany(e => e.Versions)
                .WithOne(v => v.Document)
                .HasForeignKey(v => v.DocumentId)
                .OnDelete(DeleteBehavior.Cascade);
            entity.HasMany(e => e.Comments)
                .WithOne(c => c.Document)
                .HasForeignKey(c => c.DocumentId)
                .OnDelete(DeleteBehavior.Cascade);
        });

        modelBuilder.Entity<DocumentVersion>(entity =>
        {
            entity.HasIndex(e => e.DocumentId);
        });

        modelBuilder.Entity<Comment>(entity =>
        {
            entity.HasIndex(e => e.DocumentId);
        });
    }
}
