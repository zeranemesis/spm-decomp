param(
    [string]$MainDol = "",
    [string]$Rel = "",
    [string]$RelLoad = ""
)

$ErrorActionPreference = "Stop"

$PortRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

if ([string]::IsNullOrWhiteSpace($MainDol)) {
    $MainDol = Join-Path $PortRoot "game\main.dol"
}
if ([string]::IsNullOrWhiteSpace($Rel)) {
    $Rel = Join-Path $PortRoot "game\relF.rel"
}

$RelBin = Join-Path $PortRoot "game\relF.bin"
$WiiCompiled = Join-Path $PortRoot "vendor\Wiicompiled"
$Translator = Join-Path $WiiCompiled "translator\src\Translator.Cli\bin\Release\net8.0\Translator.Cli.dll"
$FunctionMap = Join-Path $PortRoot "generated\SPM.map"
$Manifest = Join-Path $PortRoot "generated\spm-eu0.yml"

$GeneratedRoot = Join-Path $PortRoot "build\generated"
$FunctionsDir = Join-Path $GeneratedRoot "functions"
$BaseMetadata = Join-Path $GeneratedRoot "base_translation_output.json"
$BaseManifestDir = Join-Path $PortRoot "build\base"
$ShardsDir = Join-Path $GeneratedRoot "build_shards"
$NativeSourceDir = Join-Path $WiiCompiled "runtime\src"

if (-not (Test-Path $MainDol)) {
    throw "Missing main.dol: $MainDol"
}

if (-not (Test-Path $Rel)) {
    if (Test-Path $RelBin) {
        $Dtk = & (Join-Path $PortRoot "get-dtk.ps1")
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        Write-Host "relF.rel is missing; decompressing relF.bin automatically..."
        & $Dtk nlzss decompress $RelBin -o $Rel
        if ($LASTEXITCODE -ne 0) {
            throw "decomp-toolkit failed to decompress relF.bin"
        }
    }
    else {
        throw "Missing relF.rel and relF.bin in $PortRoot\game"
    }
}

if (-not (Test-Path $Translator)) {
    & (Join-Path $PortRoot "bootstrap.ps1") -SkipTests
}

New-Item -ItemType Directory -Force -Path $GeneratedRoot | Out-Null
New-Item -ItemType Directory -Force -Path $FunctionsDir | Out-Null
New-Item -ItemType Directory -Force -Path $BaseManifestDir | Out-Null
New-Item -ItemType Directory -Force -Path $ShardsDir | Out-Null

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
Write-Host "SPM translation paths:"
Write-Host "  functions : $FunctionsDir"
Write-Host "  metadata  : $BaseMetadata"
Write-Host "  manifest  : $BaseManifestDir"
Write-Host "  shards    : $ShardsDir"
Write-Host "  runtime   : $NativeSourceDir"
Write-Host ""
Write-Host "Starting SPM static translation from $Entry"

$translateArgs = @(
    $Translator, "translate-recursive", $Entry,
    "--project", $Manifest,
    "--outdir", $FunctionsDir,
    "--output-metadata", $BaseMetadata,
    "--prune-stale"
)

$baseManifestArgs = @(
    $Translator, "emit-base-manifest",
    "--project", $Manifest,
    "--out", $BaseManifestDir,
    "--functions-dir", $FunctionsDir,
    "--translation-output-metadata", $BaseMetadata
)

$shardArgs = @(
    $Translator, "emit-build-shards",
    "--project", $Manifest,
    "--base-metadata", $BaseMetadata,
    "--base-functions-dir", $FunctionsDir,
    "--native-source-dir", $NativeSourceDir,
    "--out", $ShardsDir
)

Push-Location $WiiCompiled
try {
    dotnet @translateArgs
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    if (-not (Test-Path $BaseMetadata)) {
        throw "Translation succeeded but metadata was not generated: $BaseMetadata"
    }

    dotnet $Translator generate-data-init --project $Manifest
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    dotnet @baseManifestArgs
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    dotnet @shardArgs
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}

$ShardManifest = Join-Path $ShardsDir "shards.cmake"
if (-not (Test-Path $ShardManifest)) {
    throw "Shard generation returned success but shards.cmake is missing: $ShardManifest"
}

Write-Host ""
Write-Host "Translation pass completed successfully."
Write-Host "Base metadata:"
Write-Host "  $BaseMetadata"
Write-Host "CMake shard graph:"
Write-Host "  $ShardManifest"
Write-Host ""
Write-Host "Next milestone: compile the generated x86-64 native product."
