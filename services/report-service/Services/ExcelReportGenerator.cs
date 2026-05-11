using System.Globalization;
using ClosedXML.Excel;
using OtterWorks.ReportService.Models;
using OtterWorks.ReportService.Utilities;

namespace OtterWorks.ReportService.Services;

public class ExcelReportGenerator : IExcelReportGenerator
{
    private readonly ILogger<ExcelReportGenerator> _logger;

    public ExcelReportGenerator(ILogger<ExcelReportGenerator> logger)
    {
        _logger = logger;
    }

    public string GenerateExcel(Report report, List<Dictionary<string, object>> data, string outputDir)
    {
        string fileName = BuildFileName(report, "xlsx");
        string filePath = Path.Combine(outputDir, fileName);
        Directory.CreateDirectory(outputDir);

        using var workbook = new XLWorkbook();

        CreateSummarySheet(workbook, report, data.Count);

        var dataSheet = workbook.Worksheets.Add("Data");
        if (data.Count > 0)
        {
            CreateDataSheet(dataSheet, data);
        }

        workbook.SaveAs(filePath);

        _logger.LogInformation("Generated Excel report: {FilePath} ({Size} bytes)", filePath, new FileInfo(filePath).Length);
        return filePath;
    }

    private static void CreateSummarySheet(XLWorkbook workbook, Report report, int rowCount)
    {
        var sheet = workbook.Worksheets.Add("Summary");

        var titleCell = sheet.Cell(1, 1);
        titleCell.Value = "OtterWorks Report";
        titleCell.Style.Font.Bold = true;
        titleCell.Style.Font.FontSize = 16;
        titleCell.Style.Font.FontColor = XLColor.DarkBlue;
        sheet.Range(1, 1, 1, 2).Merge();

        sheet.Cell(3, 1).Value = "Report Name:";
        sheet.Cell(3, 1).Style.Font.Bold = true;
        sheet.Cell(3, 1).Style.Alignment.Horizontal = XLAlignmentHorizontalValues.Right;
        sheet.Cell(3, 2).Value = report.ReportName;

        sheet.Cell(4, 1).Value = "Category:";
        sheet.Cell(4, 1).Style.Font.Bold = true;
        sheet.Cell(4, 1).Style.Alignment.Horizontal = XLAlignmentHorizontalValues.Right;
        sheet.Cell(4, 2).Value = report.Category.ToString();

        sheet.Cell(5, 1).Value = "Period:";
        sheet.Cell(5, 1).Style.Font.Bold = true;
        sheet.Cell(5, 1).Style.Alignment.Horizontal = XLAlignmentHorizontalValues.Right;
        sheet.Cell(5, 2).Value = $"{ReportDateUtils.ToDisplayString(report.DateFrom)} to {ReportDateUtils.ToDisplayString(report.DateTo)}";

        sheet.Cell(6, 1).Value = "Generated:";
        sheet.Cell(6, 1).Style.Font.Bold = true;
        sheet.Cell(6, 1).Style.Alignment.Horizontal = XLAlignmentHorizontalValues.Right;
        sheet.Cell(6, 2).Value = ReportDateUtils.ToDisplayString(DateTime.UtcNow);

        sheet.Cell(7, 1).Value = "Total Rows:";
        sheet.Cell(7, 1).Style.Font.Bold = true;
        sheet.Cell(7, 1).Style.Alignment.Horizontal = XLAlignmentHorizontalValues.Right;
        sheet.Cell(7, 2).Value = rowCount;

        sheet.Cell(8, 1).Value = "Requested By:";
        sheet.Cell(8, 1).Style.Font.Bold = true;
        sheet.Cell(8, 1).Style.Alignment.Horizontal = XLAlignmentHorizontalValues.Right;
        sheet.Cell(8, 2).Value = report.RequestedBy;

        sheet.Columns().AdjustToContents();
    }

    private static void CreateDataSheet(IXLWorksheet sheet, List<Dictionary<string, object>> data)
    {
        var columns = data[0].Keys.ToList();

        for (int colIdx = 0; colIdx < columns.Count; colIdx++)
        {
            var cell = sheet.Cell(1, colIdx + 1);
            cell.Value = FormatColumnName(columns[colIdx]);
            cell.Style.Font.Bold = true;
            cell.Style.Font.FontColor = XLColor.White;
            cell.Style.Fill.BackgroundColor = XLColor.DarkBlue;
            cell.Style.Border.BottomBorder = XLBorderStyleValues.Thin;
            cell.Style.Alignment.Horizontal = XLAlignmentHorizontalValues.Center;
        }

        for (int rowIdx = 0; rowIdx < data.Count; rowIdx++)
        {
            int excelRow = rowIdx + 2;
            for (int colIdx = 0; colIdx < columns.Count; colIdx++)
            {
                var cell = sheet.Cell(excelRow, colIdx + 1);
                string value = data[rowIdx].TryGetValue(columns[colIdx], out var val) && val != null
                    ? Convert.ToString(val, CultureInfo.InvariantCulture) ?? string.Empty
                    : string.Empty;
                cell.Value = value;

                cell.Style.Border.OutsideBorder = XLBorderStyleValues.Thin;

                if (rowIdx % 2 == 1)
                {
                    cell.Style.Fill.BackgroundColor = XLColor.FromArgb(236, 240, 241);
                }
            }
        }

        sheet.Columns().AdjustToContents();

        if (data.Count > 0)
        {
            sheet.Range(1, 1, data.Count + 1, columns.Count).SetAutoFilter();
        }
    }

    private static string FormatColumnName(string columnName)
    {
        if (string.IsNullOrWhiteSpace(columnName))
        {
            return string.Empty;
        }

        string replaced = columnName.Replace("_", " ");
        return CultureInfo.InvariantCulture.TextInfo.ToTitleCase(replaced);
    }

    private static string BuildFileName(Report report, string extension)
    {
        string safeName = System.Text.RegularExpressions.Regex.Replace(report.ReportName, "[^a-zA-Z0-9]", "_").ToLowerInvariant();
        return $"{safeName}_{ReportDateUtils.ToFileNameString(DateTime.UtcNow)}.{extension}";
    }
}
