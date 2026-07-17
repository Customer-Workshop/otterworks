using System;
using System.Globalization;
using System.Windows;
using System.Windows.Data;

namespace OtterWorks.Desktop.Mvvm
{
    /// <summary>
    /// Converts a string to <see cref="Visibility"/>: non-empty becomes Visible, otherwise Collapsed.
    /// </summary>
    public class StringToVisibilityConverter : IValueConverter
    {
        public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
        {
            string text = value as string;
            return string.IsNullOrWhiteSpace(text) ? Visibility.Collapsed : Visibility.Visible;
        }

        public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
        {
            throw new NotSupportedException();
        }
    }

    /// <summary>Inverts a boolean value (for e.g. enabling controls when not busy).</summary>
    public class InverseBooleanConverter : IValueConverter
    {
        public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
        {
            return value is bool b ? !b : (object)true;
        }

        public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
        {
            return value is bool b ? !b : (object)false;
        }
    }
}
