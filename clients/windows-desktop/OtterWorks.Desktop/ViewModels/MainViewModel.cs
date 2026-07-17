using OtterWorks.Desktop.Mvvm;
using OtterWorks.Desktop.Services;

namespace OtterWorks.Desktop.ViewModels
{
    /// <summary>
    /// Root view model. Owns the shared API client and session, and swaps the active
    /// child view model (login / register / documents) to drive navigation.
    /// </summary>
    public class MainViewModel : ObservableObject
    {
        private readonly OtterWorksApiClient _api;
        private readonly SessionState _session;
        private ObservableObject _currentViewModel;

        public MainViewModel(OtterWorksApiClient api, SessionState session)
        {
            _api = api;
            _session = session;

            if (_session.IsAuthenticated)
            {
                ShowDocuments();
            }
            else
            {
                ShowLogin();
            }
        }

        public ObservableObject CurrentViewModel
        {
            get => _currentViewModel;
            private set => SetProperty(ref _currentViewModel, value);
        }

        public bool IsAuthenticated => _session.IsAuthenticated;

        public string CurrentUserName => _session.User?.DisplayName ?? _session.User?.Email;

        public void ShowLogin()
        {
            CurrentViewModel = new LoginViewModel(_api, _session, this);
            RaiseSessionChanged();
        }

        public void ShowRegister()
        {
            CurrentViewModel = new RegisterViewModel(_api, _session, this);
            RaiseSessionChanged();
        }

        public void ShowDocuments()
        {
            CurrentViewModel = new DocumentsViewModel(_api, this);
            RaiseSessionChanged();
        }

        public void Logout()
        {
            _session.Clear();
            ShowLogin();
        }

        private void RaiseSessionChanged()
        {
            OnPropertyChanged(nameof(IsAuthenticated));
            OnPropertyChanged(nameof(CurrentUserName));
        }
    }
}
