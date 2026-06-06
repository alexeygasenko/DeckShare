$ErrorActionPreference = "Stop"
$dotnet = Join-Path $PSScriptRoot ".dotnet\dotnet.exe"
if (-not (Test-Path $dotnet)) {
    $dotnet = "dotnet"
}

& $dotnet publish "$PSScriptRoot\src\DeckShare\DeckShare.csproj" `
    --configuration Release `
    --runtime win-x64 `
    --self-contained true `
    -p:PublishSingleFile=true `
    -p:EnableCompressionInSingleFile=true `
    -p:IncludeNativeLibrariesForSelfExtract=true `
    -p:DebugType=None `
    -p:DebugSymbols=false `
    --output "$PSScriptRoot\dist"

Write-Host "Portable build: $PSScriptRoot\dist\DeckShare.exe"
