using System;
using System.Collections.Generic;
using Newtonsoft.Json;

namespace OtterWorks.Desktop.Models
{
    /// <summary>Request body for POST /documents.</summary>
    public class CreateDocumentRequest
    {
        [JsonProperty("title")]
        public string Title { get; set; }
    }

    /// <summary>
    /// A document as returned by the document service. Fields are snake_case.
    /// </summary>
    public class Document
    {
        [JsonProperty("id")]
        public string Id { get; set; }

        [JsonProperty("title")]
        public string Title { get; set; }

        [JsonProperty("content")]
        public string Content { get; set; }

        [JsonProperty("content_type")]
        public string ContentType { get; set; }

        [JsonProperty("owner_id")]
        public string OwnerId { get; set; }

        [JsonProperty("folder_id")]
        public string FolderId { get; set; }

        [JsonProperty("is_deleted")]
        public bool IsDeleted { get; set; }

        [JsonProperty("word_count")]
        public int WordCount { get; set; }

        [JsonProperty("version")]
        public int Version { get; set; }

        [JsonProperty("created_at")]
        public DateTimeOffset? CreatedAt { get; set; }

        [JsonProperty("updated_at")]
        public DateTimeOffset? UpdatedAt { get; set; }
    }

    /// <summary>Paged response for GET /documents.</summary>
    public class DocumentListResponse
    {
        [JsonProperty("items")]
        public List<Document> Items { get; set; } = new List<Document>();

        [JsonProperty("total")]
        public int Total { get; set; }

        [JsonProperty("page")]
        public int Page { get; set; }

        [JsonProperty("size")]
        public int Size { get; set; }

        [JsonProperty("pages")]
        public int Pages { get; set; }
    }
}
