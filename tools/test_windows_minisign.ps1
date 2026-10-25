$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root

if (Get-ChildItem -Path (Join-Path $Root "release\tools\minisign-*-windows-*") -ErrorAction SilentlyContinue) {
  throw "The clean-machine verifier test requires a fresh checkout; existing caches are never deleted"
}
$Diagnostics = [IO.Path]::GetTempFileName()
try {
  $SavedErrorActionPreference = $ErrorActionPreference
  try {
    $ErrorActionPreference = "SilentlyContinue"
    & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools/minisign.ps1 -Portable -NoSystemChanges *> $Diagnostics
    $MissingExitCode = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $SavedErrorActionPreference
  }
  if ($MissingExitCode -eq 0) { throw "A missing verifier must fail when downloads are forbidden" }

  & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools/minisign.ps1 -Portable
  if ($LASTEXITCODE -ne 0) { throw "Clean-machine portable verifier bootstrap failed" }
  & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools/minisign.ps1 -Portable -NoSystemChanges
  if ($LASTEXITCODE -ne 0) { throw "A verified cached tool must work without downloads" }

  & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools/python.ps1 -m unittest discover -s tools -p test_minisign_bootstrap.py
  if ($LASTEXITCODE -ne 0) { throw "Verifier cache, architecture or real cryptographic regressions failed" }
  Write-Host "Clean-machine Windows verifier bootstrap and cryptographic checks passed."
} finally {
  Remove-Item -LiteralPath $Diagnostics -Force
}
