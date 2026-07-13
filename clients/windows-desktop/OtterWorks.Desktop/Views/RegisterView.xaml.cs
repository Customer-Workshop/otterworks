using System.Windows.Controls;
using OtterWorks.Desktop.ViewModels;

namespace OtterWorks.Desktop.Views
{
    public partial class RegisterView : UserControl
    {
        public RegisterView()
        {
            InitializeComponent();
        }

        private void PasswordInput_PasswordChanged(object sender, System.Windows.RoutedEventArgs e)
        {
            if (DataContext is RegisterViewModel vm)
            {
                vm.Password = PasswordInput.Password;
            }
        }
    }
}
