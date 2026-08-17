[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

foreach ($RelativePath in @("dist", "release", "src-tauri/target")) {
  $Path = Join-Path $Root $RelativePath
  if (Test-Path -LiteralPath $Path) {
    Write-Host "+ Remove-Item -Recurse -Force $Path"
    Remove-Item -LiteralPath $Path -Recurse -Force
  }
}
