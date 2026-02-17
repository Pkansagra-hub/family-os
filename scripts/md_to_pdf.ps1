# save as: D:\familyos\scripts\md_to_pdf_fixed.ps1

param(
    [string]$MarkdownFile = "D:\familyos\k1\concierge\concierge.md",
    [string]$CssFile = "D:\familyos\scripts\pdfconvert.css",
    [string]$OutputName = "K1_Concierge_Spec.pdf"
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "K1 Concierge PDF Generator (Fixed Version)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if files exist
if (-not (Test-Path $MarkdownFile)) {
    Write-Host "❌ ERROR: Markdown file not found: $MarkdownFile" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $CssFile)) {
    Write-Host "❌ ERROR: CSS file not found: $CssFile" -ForegroundColor Red
    exit 1
}

Write-Host "📄 Input MD: $MarkdownFile" -ForegroundColor Yellow
Write-Host "🎨 CSS File: $CssFile" -ForegroundColor Yellow
Write-Host "📊 Output PDF: $OutputName" -ForegroundColor Yellow
Write-Host ""

# Find pandoc
$pandocPath = $null
$possiblePaths = @(
    "C:\Program Files\Pandoc\pandoc.exe",
    "C:\Program Files (x86)\Pandoc\pandoc.exe",
    "$env:LOCALAPPDATA\Pandoc\pandoc.exe"
)

foreach ($path in $possiblePaths) {
    if (Test-Path $path) {
        $pandocPath = $path
        break
    }
}

if (-not $pandocPath) {
    Write-Host "❌ Pandoc not found. Please install from: https://pandoc.org/installing.html" -ForegroundColor Red
    Write-Host "After installing, run this script again." -ForegroundColor Yellow
    exit 1
}

Write-Host "✅ Found Pandoc at: $pandocPath" -ForegroundColor Green

# Find wkhtmltopdf
$wkhtmlPath = $null
$wkpossiblePaths = @(
    "C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe",
    "C:\Program Files (x86)\wkhtmltopdf\bin\wkhtmltopdf.exe"
)

foreach ($path in $wkpossiblePaths) {
    if (Test-Path $path) {
        $wkhtmlPath = $path
        break
    }
}

# Step 1: Convert to HTML
Write-Host "`nStep 1: Generating HTML..." -ForegroundColor Green
$htmlFile = [System.IO.Path]::GetFileNameWithoutExtension($OutputName) + ".html"
$htmlFullPath = Join-Path (Get-Location) $htmlFile

& $pandocPath "$MarkdownFile" `
    -o "$htmlFullPath" `
    --css "$CssFile" `
    --self-contained `
    --metadata title="K1 Concierge Module Specification" `
    --metadata author="K1 Team" `
    --metadata date="2026-02-16"

if ($LASTEXITCODE -ne 0 -or -not (Test-Path $htmlFullPath)) {
    Write-Host "❌ HTML generation failed!" -ForegroundColor Red
    exit 1
}

Write-Host "✅ HTML generated: $htmlFile" -ForegroundColor Green

# Step 2: Convert to PDF
Write-Host "`nStep 2: Converting to PDF..." -ForegroundColor Green
$pdfGenerated = $false

# Method 1: wkhtmltopdf if available
if ($wkhtmlPath) {
    Write-Host "   Using wkhtmltopdf..." -ForegroundColor Yellow
    $pdfFullPath = Join-Path (Get-Location) $OutputName

    & $wkhtmlPath --enable-local-file-access --quiet "$htmlFullPath" "$pdfFullPath"

    if ($LASTEXITCODE -eq 0 -and (Test-Path $pdfFullPath)) {
        $pdfGenerated = $true
        Write-Host "   ✅ wkhtmltopdf succeeded" -ForegroundColor Green
    }
    else {
        Write-Host "   ⚠ wkhtmltopdf failed" -ForegroundColor Red
    }
}

# Method 2: Pandoc with HTML5 if wkhtmltopdf failed
if (-not $pdfGenerated) {
    Write-Host "   Trying Pandoc HTML engine..." -ForegroundColor Yellow
    $pdfFullPath = Join-Path (Get-Location) $OutputName

    & $pandocPath "$htmlFullPath" -o "$pdfFullPath" --pdf-engine=wkhtmltopdf

    if ($LASTEXITCODE -eq 0 -and (Test-Path $pdfFullPath)) {
        $pdfGenerated = $true
        Write-Host "   ✅ Pandoc engine succeeded" -ForegroundColor Green
    }
    else {
        Write-Host "   ⚠ Pandoc engine failed" -ForegroundColor Red
    }
}

# Final result
Write-Host ""
if ($pdfGenerated) {
    $fileSize = (Get-Item $pdfFullPath).Length / 1KB
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "✅ SUCCESS! PDF Generated:" -ForegroundColor Green
    Write-Host "   File: $OutputName" -ForegroundColor White
    Write-Host "   Size: $([math]::Round($fileSize, 2)) KB" -ForegroundColor White
    Write-Host "   Location: $pdfFullPath" -ForegroundColor White
    Write-Host "========================================" -ForegroundColor Cyan

    # Open the PDF
    $openNow = Read-Host "`nOpen PDF now? (y/n)"
    if ($openNow -eq 'y') {
        Start-Process $pdfFullPath
    }
}
else {
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "❌ FAILED: Could not generate PDF" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please install wkhtmltopdf:" -ForegroundColor Yellow
    Write-Host "1. Download from: https://wkhtmltopdf.org/downloads.html" -ForegroundColor Yellow
    Write-Host "2. Install (use default settings)" -ForegroundColor Yellow
    Write-Host "3. Run this script again" -ForegroundColor Yellow
}

# Clean up
$keepHtml = Read-Host "`nKeep HTML file? (y/n)"
if ($keepHtml -ne 'y' -and (Test-Path $htmlFullPath)) {
    Remove-Item $htmlFullPath
    Write-Host "🧹 Cleaned up HTML file" -ForegroundColor Gray
}
