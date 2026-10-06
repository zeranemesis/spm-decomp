param(
    [string]$MainDol = "",
    [string]$Rel = "",
    [string]$RelLoad = ""
)

$ErrorActionPreference = "Stop"
$PortRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $PortRoot

if ([string]::IsNullOrWhiteSpace($MainDol)) {
    $MainDol = Join-Path $PortRoot "game\main.dol"
}
if ([string]::IsNullOrWhiteSpace($Rel)) {
    $Rel = Join-Path $PortRoot "game\relF.rel"
}

$WiiCompiled = Join-Path $PortRoot "vendor\Wiicompiled"
$Translator = Join-Path $WiiCompiled "translator\src\Translator.Cli\bin\Release\net8.0\Translator.Cli.dll"
$FunctionMap = Join-Path $PortRoot "generated\SPM.map"
$Manifest = Join-Path $PortRoot "generated\spm-eu0.yml"

if (-not (Test-Path $Translator)) {
    & (Join-Path $PortRoot "bootstrap.ps1")
}

python (Join-Path $PortRoot "scripts\make_function_map.py") --output $FunctionMap
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$manifestArgs = @(
    (Join-Path $PortRoot "scripts\make_manifest.py"),
    "--dol", $MainDol,
    "--rel", $Rel,
    "--function-map", $FunctionMap,
    "--output", $Manifest
)
if (-not [string]::IsNullOrWhiteSpace($RelLoad)) {
    $manifestArgs += @("--rel-load", $RelLoad)
}

python @manifestArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$dolInfoJson = python (Join-Path $PortRoot "scripts\inspect_dol.py") $MainDol --json
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$dolInfo = $dolInfoJson | ConvertFrom-Json
$Entry = ("0x{0:X8}" -f [uint32]$dolInfo.entry_point)

Write-Host ""
Write-Host "Starting SPM static translation from $Entry"

Push-Location $WiiCompiled
try {
    dotnet $Translator translate-recursive $Entry --project $Manifest --prune-stale
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    dotnet $Translator generate-data-init --project $Manifest
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    dotnet $Translator emit-base-manifest --project $Manifest
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    dotnet $Translator emit-build-shards --project $Manifest
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "Translation pass completed."
Write-Host "Generated output:"
Write-Host "  $(Join-Path $PortRoot 'build\generated')"
Write-Host ""
Write-Host "Next milestone: classify missing native Wii services and reach the first host executable."
