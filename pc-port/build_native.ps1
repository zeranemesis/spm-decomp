param(
    [int]$Parallel = 0,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0

$PortRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$WiiCompiled = Join-Path $PortRoot "vendor\Wiicompiled"
$GeneratedRoot = Join-Path $PortRoot "build\generated"
$ShardManifest = Join-Path $GeneratedRoot "build_shards\shards.cmake"
$NativeBuild = Join-Path $PortRoot "build\native"
$PortableTools = Join-Path $PortRoot "vendor\portable-tools"
$Dependencies = Join-Path $PortRoot "vendor\dependencies"
$RuntimeGenerated = Join-Path $WiiCompiled "generated"

foreach ($required in @(
    (Join-Path $GeneratedRoot "RuntimeConfig.h"),
    (Join-Path $GeneratedRoot "data_sections_init.cpp"),
    (Join-Path $GeneratedRoot "guest_symbol_table.cpp"),
    (Join-Path $GeneratedRoot "data_sections_init_blobs.S"),
    $ShardManifest,
    (Join-Path $WiiCompiled "runtime\CMakeLists.txt"),
    (Join-Path $WiiCompiled "Launcher\Prepare-PortableTools.ps1"),
    (Join-Path $WiiCompiled "Launcher\Prepare-Dependencies.ps1"),
    (Join-Path $WiiCompiled "Launcher\NativeBuildFlags.ps1")
)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required native-build input is missing: $required"
    }
}

if ($Clean -and (Test-Path $NativeBuild)) {
    Write-Host "Removing previous native build..."
    Remove-Item -LiteralPath $NativeBuild -Recurse -Force
}

Write-Host "Preparing pinned Windows toolchain..."
& (Join-Path $WiiCompiled "Launcher\Prepare-PortableTools.ps1") -Destination $PortableTools
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Preparing pinned Aurora/Dawn dependencies..."
& (Join-Path $WiiCompiled "Launcher\Prepare-Dependencies.ps1") -Destination $Dependencies
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# WiiCompiled runtime includes generated/RuntimeConfig.h and looks for the data/symbol
# initializer beside it. Only these small generated files are staged into the vendored
# runtime tree. The translated shards remain in pc-port/build and shards.cmake uses
# absolute paths to them.
New-Item -ItemType Directory -Force -Path $RuntimeGenerated | Out-Null
Copy-Item -Force (Join-Path $GeneratedRoot "RuntimeConfig.h") $RuntimeGenerated
Copy-Item -Force (Join-Path $GeneratedRoot "data_sections_init.cpp") $RuntimeGenerated
Copy-Item -Force (Join-Path $GeneratedRoot "guest_symbol_table.cpp") $RuntimeGenerated
Copy-Item -Force (Join-Path $GeneratedRoot "data_sections_init_blobs.S") $RuntimeGenerated

Write-Host ""
Write-Host "Applying SPM-specific runtime bootstrap patches..."
python (Join-Path $PortRoot "scripts\patch_wiicompiled_runtime.py") $WiiCompiled
if ($LASTEXITCODE -ne 0) { throw "SPM runtime patching failed with exit code $LASTEXITCODE" }

. (Join-Path $WiiCompiled "Launcher\NativeBuildFlags.ps1")

$CMake = Join-Path $PortableTools "CMake\bin\cmake.exe"
$Ninja = Join-Path $PortableTools "Ninja\ninja.exe"
$ToolchainBin = Join-Path $PortableTools "llvm-mingw\bin"
$CC = Join-Path $ToolchainBin "x86_64-w64-mingw32-clang.exe"
$CXX = Join-Path $ToolchainBin "x86_64-w64-mingw32-clang++.exe"
$Windres = Join-Path $ToolchainBin "x86_64-w64-mingw32-windres.exe"

foreach ($tool in @($CMake, $Ninja, $CC, $CXX, $Windres)) {
    if (-not (Test-Path -LiteralPath $tool -PathType Leaf)) {
        throw "Pinned build tool is missing: $tool"
    }
}

$MemoryGiB = [math]::Max(1, [math]::Floor((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB))
$CpuCount = [Environment]::ProcessorCount
if ($Parallel -gt 0) {
    $TranslatedJobs = $Parallel
    $GlobalJobs = $Parallel
} else {
    $TranslatedJobs = [math]::Max(1, [math]::Min($CpuCount, [math]::Floor($MemoryGiB / 2)))
    $GlobalJobs = [math]::Max($TranslatedJobs, $CpuCount)
}

Write-Host ""
Write-Host "Native build configuration:"
Write-Host "  CPU threads              : $CpuCount"
Write-Host "  RAM                      : $MemoryGiB GiB"
Write-Host "  translated compile jobs  : $TranslatedJobs"
Write-Host "  global Ninja jobs        : $GlobalJobs"
Write-Host "  shard graph              : $ShardManifest"
Write-Host "  build directory          : $NativeBuild"

$Additional = @(
    "-DMKW_TRANSLATED_COMPILE_JOBS=$TranslatedJobs",
    "-DMKW_TRANSLATED_SHARD_MANIFEST=$(ConvertTo-MkwCMakePath $ShardManifest)"
)

$Configure = Get-MkwNativeConfigureArguments `
    -SourceDirectory (Join-Path $WiiCompiled "runtime") `
    -BuildDirectory $NativeBuild `
    -Ninja $Ninja `
    -CCompiler $CC `
    -CxxCompiler $CXX `
    -ResourceCompiler $Windres `
    -DependenciesDirectory $Dependencies `
    -AdditionalArguments $Additional

$OldPath = $env:PATH
$OldDotnet = $env:DOTNET_ROOT
try {
    $env:PATH = Get-MkwToolchainPath $PortableTools
    Remove-Item Env:DOTNET_ROOT -ErrorAction SilentlyContinue

    Write-Host ""
    Write-Host "Configuring WiiCompiled runtime for SPM..."
    & $CMake @Configure
    if ($LASTEXITCODE -ne 0) { throw "CMake configure failed with exit code $LASTEXITCODE" }

    Write-Host ""
    Write-Host "Compiling translated SPM + Wii runtime..."
    & $CMake --build $NativeBuild --target WiiCompiled --parallel $GlobalJobs
    if ($LASTEXITCODE -ne 0) { throw "Native compile failed with exit code $LASTEXITCODE" }
}
finally {
    $env:PATH = $OldPath
    if ($null -ne $OldDotnet) { $env:DOTNET_ROOT = $OldDotnet }
}

$Exe = Join-Path $NativeBuild "WiiCompiled.exe"
if (-not (Test-Path -LiteralPath $Exe -PathType Leaf)) {
    throw "Build returned success but executable is missing: $Exe"
}

$SpmExe = Join-Path $NativeBuild "SPM.exe"
Copy-Item -Force $Exe $SpmExe

Write-Host ""
Write-Host "Native compile succeeded."
Write-Host "First SPM executable candidate:"
Write-Host "  $SpmExe"
Write-Host ""
Write-Host "Do not expect gameplay yet: the next phase is replacing Wii/MKW-specific runtime behavior"
Write-Host "with verified SPM HLE bridges and then reaching the first boot/frame."
