using Microsoft.EntityFrameworkCore;
using OtterWorks.ReportService.Models;

namespace OtterWorks.ReportService.Data;

public class ReportDbContext : DbContext
{
    public ReportDbContext(DbContextOptions<ReportDbContext> options)
        : base(options)
    {
    }

    public DbSet<Report> Reports { get; set; } = null!;

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<Report>(entity =>
        {
            entity.ToTable("reports");
            entity.HasKey(e => e.Id);
            entity.Property(e => e.Id).HasColumnName("id").UseIdentityAlwaysColumn();
            entity.Property(e => e.ReportName).HasColumnName("report_name").IsRequired();
            entity.Property(e => e.Category).HasColumnName("category").HasConversion<string>().IsRequired();
            entity.Property(e => e.ReportType).HasColumnName("report_type").HasConversion<string>().IsRequired();
            entity.Property(e => e.Status).HasColumnName("status").HasConversion<string>().IsRequired();
            entity.Property(e => e.RequestedBy).HasColumnName("requested_by").IsRequired();
            entity.Property(e => e.DateFrom).HasColumnName("date_from");
            entity.Property(e => e.DateTo).HasColumnName("date_to");
            entity.Property(e => e.CreatedAt).HasColumnName("created_at").IsRequired();
            entity.Property(e => e.CompletedAt).HasColumnName("completed_at");
            entity.Property(e => e.FilePath).HasColumnName("file_path");
            entity.Property(e => e.FileSizeBytes).HasColumnName("file_size_bytes");
            entity.Property(e => e.RowCount).HasColumnName("row_count");
            entity.Property(e => e.ErrorMessage).HasColumnName("error_message");
            entity.Property(e => e.Parameters).HasColumnName("parameters");
        });
    }
}
