# PowerShell script to count lines of code by file type across the full repository
$root = "D:\familyos"

# Excluded directory names anywhere in the tree
$excludedDirPattern = '\\(__pycache__|\.venv|venv|env|\.git|node_modules|wheels|dist|build)\\'

$mdLines = 0
$pyLines = 0
$otherLines = 0
$totalFiles = 0
$otherByExtension = @{}

function Get-LineCount {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $reader = $null
    try {
        $reader = [System.IO.File]::OpenText($Path)
        $count = 0
        while ($null -ne $reader.ReadLine()) {
            $count += 1
        }
        return $count
    }
    finally {
        if ($null -ne $reader) {
            $reader.Dispose()
        }
    }
}

$files = Get-ChildItem -Path $root -Recurse -File -ErrorAction SilentlyContinue |
Where-Object { $_.FullName -notmatch $excludedDirPattern }

foreach ($file in $files) {
    try {
        $lines = Get-LineCount -Path $file.FullName
    }
    catch {
        continue
    }

    $totalFiles += 1

    switch ($file.Extension.ToLower()) {
        ".md" { $mdLines += $lines }
        ".py" { $pyLines += $lines }
        default {
            $otherLines += $lines

            $ext = $file.Extension.ToLower()
            if ([string]::IsNullOrWhiteSpace($ext)) {
                $ext = "[noext]"
            }

            if (-not $otherByExtension.ContainsKey($ext)) {
                $otherByExtension[$ext] = 0
            }

            $otherByExtension[$ext] += $lines
        }
    }
}

Write-Host "===== FULL REPO TOTALS ====="
Write-Host "Root: $root"
Write-Host "Files scanned: $totalFiles"
Write-Host "MD lines (documentation): $mdLines"
Write-Host "PY lines: $pyLines"
Write-Host "Other lines (all other languages/types): $otherLines"
Write-Host "Total lines overall: $($mdLines + $pyLines + $otherLines)"
Write-Host ""

Write-Host "===== OTHER LINES BY EXTENSION ====="
if ($otherByExtension.Count -eq 0) {
    Write-Host "No non-.md/.py files found."
}
else {
    foreach ($item in $otherByExtension.GetEnumerator() | Sort-Object -Property Value -Descending) {
        Write-Host ("{0,-12} {1,10}" -f $item.Key, $item.Value)
    }
}
