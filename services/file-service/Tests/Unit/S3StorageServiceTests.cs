using Amazon.S3;
using Amazon.S3.Model;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Moq;
using OtterWorks.FileService.Config;
using OtterWorks.FileService.Services;

namespace FileService.Tests.Unit;

public class S3StorageServiceTests
{
    private readonly Mock<IAmazonS3> _mockS3;
    private readonly S3StorageService _service;

    public S3StorageServiceTests()
    {
        _mockS3 = new Mock<IAmazonS3>();
        var options = Options.Create(new AwsSettings { S3Bucket = "test-bucket" });
        _service = new S3StorageService(
            _mockS3.Object,
            options,
            Mock.Of<ILogger<S3StorageService>>());
    }

    [Fact]
    public async Task UploadObject_CallsPutObject()
    {
        _mockS3
            .Setup(s => s.PutObjectAsync(It.IsAny<PutObjectRequest>(), default))
            .ReturnsAsync(new PutObjectResponse());

        using var stream = new MemoryStream(new byte[] { 1, 2, 3 });
        await _service.UploadObjectAsync("test-key", stream, "application/octet-stream");

        _mockS3.Verify(s => s.PutObjectAsync(
            It.Is<PutObjectRequest>(r =>
                r.BucketName == "test-bucket" &&
                r.Key == "test-key" &&
                r.ContentType == "application/octet-stream"),
            default), Times.Once);
    }

    [Fact]
    public async Task DeleteObject_CallsDeleteObject()
    {
        _mockS3
            .Setup(s => s.DeleteObjectAsync(It.IsAny<string>(), It.IsAny<string>(), default))
            .ReturnsAsync(new DeleteObjectResponse());

        await _service.DeleteObjectAsync("test-key");

        _mockS3.Verify(s => s.DeleteObjectAsync("test-bucket", "test-key", default), Times.Once);
    }

    [Fact]
    public async Task CopyObject_CallsCopyObject()
    {
        _mockS3
            .Setup(s => s.CopyObjectAsync(It.IsAny<CopyObjectRequest>(), default))
            .ReturnsAsync(new CopyObjectResponse());

        await _service.CopyObjectAsync("source-key", "dest-key");

        _mockS3.Verify(s => s.CopyObjectAsync(
            It.Is<CopyObjectRequest>(r =>
                r.SourceBucket == "test-bucket" &&
                r.SourceKey == "source-key" &&
                r.DestinationBucket == "test-bucket" &&
                r.DestinationKey == "dest-key"),
            default), Times.Once);
    }

    [Fact]
    public async Task DownloadObject_ReturnsStream()
    {
        var responseStream = new MemoryStream(new byte[] { 4, 5, 6 });
        _mockS3
            .Setup(s => s.GetObjectAsync(It.IsAny<string>(), It.IsAny<string>(), default))
            .ReturnsAsync(new GetObjectResponse { ResponseStream = responseStream });

        var result = await _service.DownloadObjectAsync("test-key");

        Assert.NotNull(result);
        Assert.True(result.Length > 0);
    }

    [Fact]
    public async Task GetPresignedUrl_ReturnsUrl()
    {
        _mockS3
            .Setup(s => s.GetPreSignedURL(It.IsAny<GetPreSignedUrlRequest>()))
            .Returns("https://example.com/presigned");

        var url = await _service.GetPresignedDownloadUrlAsync("test-key", 3600);

        Assert.Equal("https://example.com/presigned", url);
    }
}
