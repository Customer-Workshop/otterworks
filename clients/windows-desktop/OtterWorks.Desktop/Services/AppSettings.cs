using System;
using System.IO;
using Newtonsoft.Json;

namespace OtterWorks.Desktop.Services
{
    /// <summary>
    /// Application configuration loaded from <c>appsettings.json</c> next to the executable.
    /// The backend base URL is configurable so the app can point at a local Docker Compose
    /// stack (the default) or any reachable OtterWorks gateway.
    /// </summary>
    public class AppSettings
    {
        private const string DefaultBaseUrl = "http://localhost:8080/api/v1";

        [JsonProperty("apiBaseUrl")]
        public string ApiBaseUrl { get; set; } = DefaultBaseUrl;

        [JsonProperty("persistTokens")]
        public bool PersistTokens { get; set; }

        public static AppSettings Load()
        {
            try
            {
                string path = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "appsettings.json");
                if (File.Exists(path))
                {
                    string json = File.ReadAllText(path);
                    AppSettings settings = JsonConvert.DeserializeObject<AppSettings>(json);
                    if (settings != null && !string.IsNullOrWhiteSpace(settings.ApiBaseUrl))
                    {
                        return settings;
                    }
                }
            }
            catch
            {
                // Fall back to defaults if the settings file is missing or malformed.
            }

            return new AppSettings { ApiBaseUrl = DefaultBaseUrl };
        }
    }
}
