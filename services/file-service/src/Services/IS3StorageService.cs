namespace OtterWorks.FileService.Services;

public interface IS3StorageService
{
    Task UploadObjectAsync(string key, Stream body, string contentType);

    Task<Stream> DownloadObjectAsync(string key);

    Task<string> GetPresignedDownloadUrlAsync(string key, int expiresInSecs);

    Task DeleteObjectAsync(string key);

    Task CopyObjectAsync(string sourceKey, string destKey);
}
