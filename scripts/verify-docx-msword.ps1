param(
    [Parameter(Mandatory = $true)]
    [string]$DocumentPath,
    [string]$PdfPath
)

$resolvedDocument = (Resolve-Path -LiteralPath $DocumentPath -ErrorAction Stop).Path
if ([IO.Path]::GetExtension($resolvedDocument) -ne '.docx') {
    throw 'DocumentPath must be a .docx file.'
}
if (-not $PdfPath) {
    $PdfPath = [IO.Path]::ChangeExtension($resolvedDocument, '.verified.pdf')
}
$resolvedPdf = [IO.Path]::GetFullPath($PdfPath)

$word = $null
$document = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $document = $word.Documents.Open($resolvedDocument, $false, $true)
    $document.Repaginate()
    $pages = $document.ComputeStatistics(2)
    $paragraphs = $document.Paragraphs.Count
    $tables = $document.Tables.Count
    $document.ExportAsFixedFormat($resolvedPdf, 17)
    [pscustomobject]@{
        Document = $resolvedDocument
        Pdf = $resolvedPdf
        Pages = $pages
        Paragraphs = $paragraphs
        Tables = $tables
        PdfBytes = (Get-Item -LiteralPath $resolvedPdf).Length
    }
}
finally {
    if ($document) { $document.Close($false) }
    if ($word) { $word.Quit() }
    if ($document) { [Runtime.InteropServices.Marshal]::ReleaseComObject($document) | Out-Null }
    if ($word) { [Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null }
}
