param(
    [Parameter(Mandatory = $true)]
    [string]$DataRoot
)

$ErrorActionPreference = "Stop"

$PortRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$GameDir = Join-Path $PortRoot "game"

$DataRoot = (Resolve-Path $DataRoot).Path
$MainDolSource = Join-Path $DataRoot "sys\main.dol"

$RelCandidates = @(
    (Join-Path $DataRoot "files\rel\relF.bin"),
    (Join-Path $DataRoot "rel\relF.bin")
)
$RelBinSource = $RelCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not (Test-Path $MainDolSource)) {
    throw "main.dol not found at: $MainDolSource"
}
if ([string]::IsNullOrWhiteSpace($RelBinSource)) {
    throw "relF.bin not found. Checked:`n  $($RelCandidates -join "`n  ")"
}

New-Item -ItemType Directory -Force -Path $GameDir | Out-Null

$MainDolDest = Join-Path $GameDir "main.dol"
$RelBinDest = Join-Path $GameDir "relF.bin"
$RelDest = Join-Path $GameDir "relF.rel"

Copy-Item -Force $MainDolSource $MainDolDest
Copy-Item -Force $RelBinSource $RelBinDest

$Dtk = & (Join-Path $PortRoot "get-dtk.ps1")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Decompressing relF.bin -> relF.rel..."
& $Dtk nlzss decompress $RelBinDest -o $RelDest
if ($LASTEXITCODE -ne 0) {
    throw "decomp-toolkit failed to decompress relF.bin"
}
if (-not (Test-Path $RelDest)) {
    throw "relF.rel was not produced"
}

Write-Host ""
Write-Host "Game files prepared:"
Get-Item $MainDolDest, $RelBinDest, $RelDest | Format-Table Name, Length

Write-Host ""
Write-Host "DOL inspection:"
python (Join-Path $PortRoot "scripts\inspect_dol.py") $MainDolDest
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Ready for:"
Write-Host "  .\translate.ps1"
