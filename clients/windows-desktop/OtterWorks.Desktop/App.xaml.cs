using System.Windows;
using OtterWorks.Desktop.Services;
using OtterWorks.Desktop.ViewModels;
using OtterWorks.Desktop.Views;

namespace OtterWorks.Desktop
{
    /// <summary>Application entry point; wires up services and shows the shell window.</summary>
    public partial class App : Application
    {
        protected override void OnStartup(StartupEventArgs e)
        {
            base.OnStartup(e);

            AppSettings settings = AppSettings.Load();
            var session = new SessionState(settings.PersistTokens);
            session.TryRestore();

            var api = new OtterWorksApiClient(settings, session);
            var mainViewModel = new MainViewModel(api, session);

            var window = new MainWindow { DataContext = mainViewModel };
            window.Show();
        }
    }
}
