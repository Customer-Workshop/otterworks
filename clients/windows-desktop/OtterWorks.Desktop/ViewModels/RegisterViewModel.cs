using System.Threading.Tasks;
using System.Windows.Input;
using OtterWorks.Desktop.Models;
using OtterWorks.Desktop.Mvvm;
using OtterWorks.Desktop.Services;

namespace OtterWorks.Desktop.ViewModels
{
    public class RegisterViewModel : ObservableObject
    {
        private readonly OtterWorksApiClient _api;
        private readonly SessionState _session;
        private readonly MainViewModel _main;

        private string _displayName;
        private string _email;
        private string _password;
        private string _errorMessage;
        private bool _isBusy;

        public RegisterViewModel(OtterWorksApiClient api, SessionState session, MainViewModel main)
        {
            _api = api;
            _session = session;
            _main = main;

            RegisterCommand = new AsyncRelayCommand(RegisterAsync, CanSubmit);
            GoToLoginCommand = new RelayCommand(() => _main.ShowLogin());
        }

        public string DisplayName
        {
            get => _displayName;
            set => SetProperty(ref _displayName, value);
        }

        public string Email
        {
            get => _email;
            set => SetProperty(ref _email, value);
        }

        public string Password
        {
            get => _password;
            set => SetProperty(ref _password, value);
        }

        public string ErrorMessage
        {
            get => _errorMessage;
            set => SetProperty(ref _errorMessage, value);
        }

        public bool IsBusy
        {
            get => _isBusy;
            set => SetProperty(ref _isBusy, value);
        }

        public ICommand RegisterCommand { get; }

        public ICommand GoToLoginCommand { get; }

        private bool CanSubmit() =>
            !IsBusy
            && !string.IsNullOrWhiteSpace(DisplayName)
            && !string.IsNullOrWhiteSpace(Email)
            && !string.IsNullOrEmpty(Password);

        private async Task RegisterAsync()
        {
            ErrorMessage = null;

            if (Password != null && Password.Length < 8)
            {
                ErrorMessage = "Password must be at least 8 characters.";
                return;
            }

            IsBusy = true;
            try
            {
                AuthResponse response = await _api
                    .RegisterAsync(DisplayName.Trim(), Email.Trim(), Password)
                    .ConfigureAwait(true);
                _session.SetSession(response);
                _main.ShowDocuments();
            }
            catch (ApiException ex)
            {
                ErrorMessage = ex.Message;
            }
            finally
            {
                IsBusy = false;
            }
        }
    }
}
