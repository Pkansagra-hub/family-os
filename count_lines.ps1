# PowerShell script to count lines of code by folder, broken down by file type
$root = "D:\familyos"

# Excluded directory names anywhere in the tree
$excludedDirPattern = '\\(__pycache__|\.venv|venv|env|\.git|node_modules|wheels|dist|build|\.mypy_cache|\.pytest_cache|\.tox|__snapshots__|\.egg-info)\\'

# Excluded file extensions (binary, build artifacts, non-authored)
$excludedExtensions = @(
    # Binary / compiled
    '.pyc', '.pyo', '.whl', '.egg', '.so', '.dll', '.exe', '.bin', '.dat', '.db',
    '.sqlite', '.sqlite3', '.faiss', '.npy', '.pkl', '.pickle', '.npz',
    # Rust build artifacts
    '.rlib', '.rmeta', '.o', '.d', '.pdb', '.lib', '.exp', '.tag', '.cargo-lock', '.timestamp',
    # Images
    '.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg', '.bmp',
    # Archives
    '.zip', '.tar', '.gz', '.bz2', '.7z', '.rar', '.pdf',
    # Data files (not authored code)
    '.csv', '.b64', '.key', '.lock', '.gitkeep',
    # Web build output
    '.css', '.js'
)

$folders = @(
    "D:\familyos\k1",
    "D:\familyos\tests",
    "D:\familyos\k0",
    "D:\familyos\poc",
    "D:\familyos\bridge",
    "D:\familyos\governance",
    "D:\familyos\docs",
    "D:\familyos\scripts"
)

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

$grandTotal = 0
$grandByExt = @{}

foreach ($folder in $folders) {
    $folderName = Split-Path $folder -Leaf

    if (-not (Test-Path $folder)) {
        Write-Host ("{0,-20} MISSING" -f $folderName)
        Write-Host ""
        continue
    }

    $files = Get-ChildItem -Path $folder -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object {
        $_.FullName -notmatch $excludedDirPattern -and
        $excludedExtensions -notcontains $_.Extension.ToLower()
    }

    $folderLines = 0
    $fileCount = 0
    $byExt = @{}

    foreach ($file in $files) {
        try {
            $lines = Get-LineCount -Path $file.FullName
        }
        catch {
            continue
        }

        $folderLines += $lines
        $fileCount += 1

        $ext = $file.Extension.ToLower()
        if ([string]::IsNullOrWhiteSpace($ext)) { $ext = "[noext]" }

        if (-not $byExt.ContainsKey($ext)) { $byExt[$ext] = 0 }
        $byExt[$ext] += $lines

        if (-not $grandByExt.ContainsKey($ext)) { $grandByExt[$ext] = 0 }
        $grandByExt[$ext] += $lines
    }

    $grandTotal += $folderLines

    Write-Host "--- $folderName ---"
    foreach ($item in $byExt.GetEnumerator() | Sort-Object -Property Value -Descending) {
        Write-Host ("    {0,-12} {1,10} lines" -f $item.Key, $item.Value)
    }
    Write-Host ("    {0,-12} {1,10} lines  ({2} files)" -f "SUBTOTAL", $folderLines, $fileCount)
    Write-Host ""
}

Write-Host "=== GRAND TOTAL BY FILE TYPE ==="
foreach ($item in $grandByExt.GetEnumerator() | Sort-Object -Property Value -Descending) {
    Write-Host ("    {0,-12} {1,10} lines" -f $item.Key, $item.Value)
}
Write-Host ""
Write-Host ("{0,-16} {1,10} lines" -f "GRAND TOTAL", $grandTotal)
