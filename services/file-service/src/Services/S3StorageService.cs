using Amazon.S3;
using Amazon.S3.Model;
using Microsoft.Extensions.Options;
using OtterWorks.FileService.Config;

namespace OtterWorks.FileService.Services;

public class S3StorageService : IS3StorageService
{
    private readonly IAmazonS3 _s3Client;
    private readonly string _bucket;
    private readonly ILogger<S3StorageService> _logger;

    public S3StorageService(IAmazonS3 s3Client, IOptions<AwsSettings> settings, ILogger<S3StorageService> logger)
    {
        _s3Client = s3Client;
        _bucket = settings.Value.S3Bucket;
        _logger = logger;
    }

    public async Task UploadObjectAsync(string key, Stream body, string contentType)
    {
        var request = new PutObjectRequest
        {
            BucketName = _bucket,
            Key = key,
            InputStream = body,
            ContentType = contentType,
        };

        await _s3Client.PutObjectAsync(request);
        _logger.LogInformation("Uploaded object to S3: {Key} in {Bucket}", key, _bucket);
    }

    public async Task<Stream> DownloadObjectAsync(string key)
    {
        var response = await _s3Client.GetObjectAsync(_bucket, key);
        return response.ResponseStream;
    }

    public async Task<string> GetPresignedDownloadUrlAsync(string key, int expiresInSecs)
    {
        var request = new GetPreSignedUrlRequest
        {
            BucketName = _bucket,
            Key = key,
            Expires = DateTime.UtcNow.AddSeconds(expiresInSecs),
            Verb = HttpVerb.GET,
        };

        var url = await Task.FromResult(_s3Client.GetPreSignedURL(request));
        return url;
    }

    public async Task DeleteObjectAsync(string key)
    {
        await _s3Client.DeleteObjectAsync(_bucket, key);
        _logger.LogInformation("Deleted object from S3: {Key}", key);
    }

    public async Task CopyObjectAsync(string sourceKey, string destKey)
    {
        var request = new CopyObjectRequest
        {
            SourceBucket = _bucket,
            SourceKey = sourceKey,
            DestinationBucket = _bucket,
            DestinationKey = destKey,
        };

        await _s3Client.CopyObjectAsync(request);
        _logger.LogInformation("Copied object in S3: {Source} -> {Dest}", sourceKey, destKey);
    }
}
