namespace OtterWorks.CollabService.Config;

public class PersistenceSettings
{
    public int IntervalMs { get; set; } = 30000;

    public int SnapshotIntervalMs { get; set; } = 300000;

    public int DocumentTtlSeconds { get; set; } = 86400;

    public int SnapshotTtlSeconds { get; set; } = 604800;

    public int MaxSnapshotsPerDocument { get; set; } = 50;
}
