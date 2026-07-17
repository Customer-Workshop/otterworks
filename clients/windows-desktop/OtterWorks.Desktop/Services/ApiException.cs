using System;
using System.Net;

namespace OtterWorks.Desktop.Services
{
    /// <summary>Raised when the OtterWorks API returns a non-success status code.</summary>
    public class ApiException : Exception
    {
        public ApiException(HttpStatusCode statusCode, string message)
            : base(message)
        {
            StatusCode = statusCode;
        }

        public HttpStatusCode StatusCode { get; }
    }
}
