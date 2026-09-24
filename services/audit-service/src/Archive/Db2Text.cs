using System.Globalization;
using System.Text;

namespace OtterWorks.AuditService.Archive;

/// <summary>Db2 text conventions shared by both stores (CONTRACTS §7 / §10.4).</summary>
public static class Db2Text
{
    private const int FractionDigits = 12;
    private static readonly Lazy<Encoding> Cp037 = new(() =>
    {
        Encoding.RegisterProvider(CodePagesEncodingProvider.Instance);
        return Encoding.GetEncoding(37);
    });

    /// <summary>Strips trailing U+0020 only; leading spaces and other whitespace are data.</summary>
    public static string RTrim(string? value) => value is null ? string.Empty : value.TrimEnd(' ');

    public static string Decimal8(decimal value) => value.ToString("0.00000000", CultureInfo.InvariantCulture);

    public static string DecodeCp037(byte[] bytes) => Cp037.Value.GetString(bytes);

    /// <summary>
    /// Db2 <c>CHAR(ts)</c> (<c>YYYY-MM-DD-HH.MM.SS.NNNNNNNNNNNN</c>) or the ADO.NET / ISO text form
    /// (<c>YYYY-MM-DD HH:MM:SS[.fraction]</c>) to the twelve-digit Db2 form.
    /// </summary>
    public static string Timestamp12(string text)
    {
        var t = text.Trim();
        var datePart = t.Substring(0, 10);
        var timePart = t.Substring(11).Replace(':', '.');
        var thirdDot = NthIndex(timePart, '.', 3);
        var hms = thirdDot >= 0 ? timePart.Substring(0, thirdDot) : timePart;
        var fraction = thirdDot >= 0 ? timePart.Substring(thirdDot + 1) : string.Empty;
        return $"{datePart}-{hms}.{fraction.PadRight(FractionDigits, '0')}";
    }

    /// <summary>DATETIME2(7) value plus the five-digit nanos tail rebuilds the original TIMESTAMP(12).</summary>
    public static string Timestamp12(DateTime dateTime2, int nanosTail)
    {
        var seven = dateTime2.ToString("yyyy-MM-dd-HH.mm.ss.fffffff", CultureInfo.InvariantCulture);
        return seven + nanosTail.ToString("00000", CultureInfo.InvariantCulture);
    }

    /// <summary>Db2 <c>YYYYMMDD</c> text to ISO <c>YYYY-MM-DD</c>; anything else (e.g. low-values) is returned trimmed.</summary>
    public static string IsoDateFromYyyymmdd(string yyyymmdd)
    {
        var t = RTrim(yyyymmdd);
        return t.Length == 8 && t.All(char.IsDigit)
            ? $"{t.Substring(0, 4)}-{t.Substring(4, 2)}-{t.Substring(6, 2)}"
            : t;
    }

    private static int NthIndex(string s, char c, int n)
    {
        var idx = -1;
        for (var i = 0; i < n; i++)
        {
            idx = s.IndexOf(c, idx + 1);
            if (idx < 0)
            {
                return -1;
            }
        }

        return idx;
    }
}
