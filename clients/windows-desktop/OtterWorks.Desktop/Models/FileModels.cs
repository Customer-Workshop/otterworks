using System;
using System.Collections.Generic;
using Newtonsoft.Json;

namespace OtterWorks.Desktop.Models
{
    /// <summary>A file as returned by the file service. Fields are snake_case.</summary>
    public class FileItem
    {
        [JsonProperty("id")]
        public string Id { get; set; }

        [JsonProperty("name")]
        public string Name { get; set; }

        [JsonProperty("size")]
        public long? Size { get; set; }

        [JsonProperty("content_type")]
        public string ContentType { get; set; }

        [JsonProperty("created_at")]
        public DateTimeOffset? CreatedAt { get; set; }
    }

    /// <summary>Paged response for GET /files.</summary>
    public class FileListResponse
    {
        [JsonProperty("files")]
        public List<FileItem> Files { get; set; } = new List<FileItem>();

        [JsonProperty("total")]
        public int Total { get; set; }

        [JsonProperty("page")]
        public int Page { get; set; }

        [JsonProperty("page_size")]
        public int PageSize { get; set; }
    }
}
