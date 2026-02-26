# count_all_tests.ps1
param(
    [string]$TestPath = "D:\familyos\tests",
    [int]$Depth = 2
)

function Get-TestCount {
    param([string]$FolderPath)

    # Run pytest collection and capture output
    $output = & python -m pytest $FolderPath --collect-only -q 2>&1 | Out-String

    # Extract the collected count
    if ($output -match 'collected (\d+) items') {
        return [int]$matches[1]
    } elseif ($output -match 'collected (\d+) tests') {
        return [int]$matches[1]
    } elseif ($output -match '(\d+) error') {
        return 0
    }
    return 0
}

Clear-Host
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "📊 TEST COUNTER - D:\familyos\tests" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Get total tests
Write-Host "`n🔍 Calculating total tests..." -ForegroundColor Yellow
$totalTests = Get-TestCount -FolderPath $TestPath
Write-Host "✅ TOTAL TESTS: $totalTests" -ForegroundColor Green

# Get top-level folder counts
Write-Host "`n📁 TOP-LEVEL FOLDERS:" -ForegroundColor Cyan
Get-ChildItem $TestPath -Directory | Where-Object { $_.Name -notmatch "__pycache__|\.pytest_cache" } | Sort-Object Name | ForEach-Object {
    $count = Get-TestCount -FolderPath $_.FullName
    $percentage = if ($totalTests -gt 0) { [math]::Round(($count / $totalTests) * 100, 1) } else { 0 }
    Write-Host "  📁 $($_.Name)/" -NoNewline
    Write-Host " - $count tests" -ForegroundColor Yellow -NoNewline
    Write-Host " ($percentage%)" -ForegroundColor Gray
}

# Get second-level folder counts (if Depth >= 2)
if ($Depth -ge 2) {
    Write-Host "`n📂 SECOND-LEVEL FOLDERS:" -ForegroundColor Cyan
    Get-ChildItem $TestPath -Directory | Where-Object { $_.Name -notmatch "__pycache__|\.pytest_cache" } | ForEach-Object {
        $parent = $_.Name
        Get-ChildItem $_.FullName -Directory | Where-Object { $_.Name -notmatch "__pycache__|\.pytest_cache" } | Sort-Object Name | ForEach-Object {
            $count = Get-TestCount -FolderPath $_.FullName
            Write-Host "  📂 $parent/$($_.Name)/" -NoNewline
            Write-Host " - $count tests" -ForegroundColor Yellow
        }
    }
}

# Summary
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "📈 SUMMARY" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Total test folders: $( (Get-ChildItem $TestPath -Directory | Where-Object { $_.Name -notmatch "__pycache__|\.pytest_cache" }).Count )" -ForegroundColor White
Write-Host "Total tests: $totalTests" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan

# Optional: Show folders with most tests
Write-Host "`n🔥 TOP 5 FOLDERS BY TEST COUNT:" -ForegroundColor Magenta
$folderCounts = @()
Get-ChildItem $TestPath -Directory -Recurse -Depth 2 | Where-Object { $_.Name -notmatch "__pycache__|\.pytest_cache" } | ForEach-Object {
    $count = Get-TestCount -FolderPath $_.FullName
    $folderCounts += [PSCustomObject]@{
        Path = $_.FullName.Replace($TestPath, "").TrimStart("\")
        Count = $count
    }
}
$folderCounts | Where-Object { $_.Count -gt 0 } | Sort-Object Count -Descending | Select-Object -First 5 | ForEach-Object {
    Write-Host "  $($_.Path) - $($_.Count) tests" -ForegroundColor Yellow
}

Write-Host "`n✅ Done! (Press any key to exit)" -ForegroundColor Green
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
