using System.Threading.Tasks;
using System.Windows.Input;
using OtterWorks.Desktop.Models;
using OtterWorks.Desktop.Mvvm;
using OtterWorks.Desktop.Services;

namespace OtterWorks.Desktop.ViewModels
{
    public class LoginViewModel : ObservableObject
    {
        private readonly OtterWorksApiClient _api;
        private readonly SessionState _session;
        private readonly MainViewModel _main;

        private string _email;
        private string _password;
        private string _errorMessage;
        private bool _isBusy;

        public LoginViewModel(OtterWorksApiClient api, SessionState session, MainViewModel main)
        {
            _api = api;
            _session = session;
            _main = main;

            LoginCommand = new AsyncRelayCommand(LoginAsync, CanSubmit);
            GoToRegisterCommand = new RelayCommand(() => _main.ShowRegister());
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

        public ICommand LoginCommand { get; }

        public ICommand GoToRegisterCommand { get; }

        private bool CanSubmit() =>
            !IsBusy && !string.IsNullOrWhiteSpace(Email) && !string.IsNullOrEmpty(Password);

        private async Task LoginAsync()
        {
            ErrorMessage = null;
            IsBusy = true;
            try
            {
                AuthResponse response = await _api.LoginAsync(Email.Trim(), Password).ConfigureAwait(true);
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
