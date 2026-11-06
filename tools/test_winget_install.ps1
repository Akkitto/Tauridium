param(
  [ValidateSet('x64', 'arm64')][Parameter(Mandatory = $true)][string]$Architecture,
  [string]$Version = '1.0.3',
  [string]$PreviousVersion = '1.0.2'
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Set-StrictMode -Version Latest
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') {
  throw 'Installer acceptance changes user installation state and is restricted to disposable GitHub-hosted Windows runners.'
}
if ([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant() -ne $Architecture.Replace('x64', 'x64')) {
  throw 'Native runner architecture does not match the installer acceptance target.'
}
$Root = Split-Path -Parent $PSScriptRoot
$RunRoot = Join-Path $env:RUNNER_TEMP ('tauridium-winget-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $RunRoot | Out-Null
$Python = (Get-Command python.exe -ErrorAction Stop).Source
$Profile = Join-Path $env:APPDATA 'dev.brani.tauridium'
if (Test-Path -LiteralPath $Profile) { throw 'Refusing to use an existing application profile.' }

function Invoke-Checked([string]$Command, [string[]]$Arguments) {
  & $Command @Arguments | Out-Host
  if ($LASTEXITCODE -ne 0) { throw ('Command failed with exit code ' + $LASTEXITCODE + ': ' + $Command) }
}
function Get-Installation {
  $Rows = @()
  foreach ($Hive in @('HKCU:', 'HKLM:')) {
    foreach ($Path in @("$Hive\Software\Microsoft\Windows\CurrentVersion\Uninstall\*", "$Hive\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*")) {
      $Rows += @(Get-ItemProperty -Path $Path -ErrorAction SilentlyContinue | Where-Object { $_.PSObject.Properties['DisplayName'] -and $_.DisplayName -eq 'Tauridium' })
    }
  }
  return $Rows
}
function Assert-Installation([string]$ExpectedVersion) {
  $Rows = @(Get-Installation)
  if ($Rows.Count -ne 1) { throw ('Expected one installation, found ' + $Rows.Count) }
  $Row = $Rows[0]
  Write-Host ('ARP: ' + (@{Name=$Row.DisplayName; Publisher=$Row.Publisher; Version=$Row.DisplayVersion; Key=$Row.PSChildName; Path=$Row.PSPath; InstallLocation=$Row.InstallLocation} | ConvertTo-Json -Compress))
  if ($Row.PSPath -notlike '*HKEY_CURRENT_USER*') { throw 'Expected a per-user NSIS installation.' }
  if ($Row.DisplayVersion -ne $ExpectedVersion) { throw 'Unexpected ARP version.' }
  if ($Row.Publisher -ne 'brani') { throw ('Unexpected ARP publisher: ' + $Row.Publisher) }
  $script:InstalledExe = Join-Path $Row.InstallLocation 'tauridium.exe'
  if (-not (Test-Path -LiteralPath $script:InstalledExe -PathType Leaf)) { throw 'Installed executable is missing.' }
  $Probe = Join-Path $RunRoot ('build-info-' + [guid]::NewGuid().ToString('N') + '.json')
  $Process = Start-Process -FilePath $script:InstalledExe -ArgumentList @('--build-info-file', ('"' + $Probe + '"')) -PassThru
  if (-not $Process.WaitForExit(30000)) { $Process.Kill(); throw 'Build-info probe timed out.' }
  if ($Process.ExitCode -ne 0) { throw 'Installed production build-info probe failed.' }
  $Info = Get-Content -LiteralPath $Probe -Raw | ConvertFrom-Json
  $Target = if ($Architecture -eq 'x64') { 'x86_64-pc-windows-msvc' } else { 'aarch64-pc-windows-msvc' }
  if ($Info.version -ne $ExpectedVersion -or $Info.target -ne $Target -or $Info.buildMode -ne 'production') { throw 'Installed executable identity differs from its manifest.' }
}
function Get-WinGet {
  $Existing = Get-Command winget.exe -ErrorAction SilentlyContinue
  if ($Existing) {
    $Text = (& $Existing.Source --version | Out-String).Trim().TrimStart('v')
    if ($LASTEXITCODE -eq 0 -and [version]$Text -ge [version]'1.28.0') { return $Existing.Source }
  }
  $Policy = Get-Content -LiteralPath (Join-Path $Root 'packaging/winget/client.json') -Raw | ConvertFrom-Json
  foreach ($Kind in @('bundle', 'dependencies')) {
    $Entry = $Policy.$Kind
    $Path = Join-Path $RunRoot $Entry.name
    Write-Host ('Downloading pinned WinGet ' + $Entry.name)
    Invoke-WebRequest -Uri ("https://github.com/microsoft/winget-cli/releases/download/v" + $Policy.version + '/' + $Entry.name) -OutFile $Path -UseBasicParsing
    if ((Get-Item -LiteralPath $Path).Length -ne $Entry.size -or (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Entry.sha256) { throw 'WinGet bootstrap size/hash mismatch.' }
  }
  $Dependencies = Join-Path $RunRoot 'dependencies'
  Expand-Archive -LiteralPath (Join-Path $RunRoot $Policy.dependencies.name) -DestinationPath $Dependencies
  $Packages = @(Get-ChildItem -LiteralPath (Join-Path $Dependencies $Architecture) -Filter '*.msix' -Recurse) + @(Get-ChildItem -LiteralPath (Join-Path $Dependencies $Architecture) -Filter '*.appx' -Recurse)
  if ($Packages.Count -eq 0) { throw 'No native WinGet dependencies in the pinned archive.' }
  Add-AppxPackage -Path (Join-Path $RunRoot $Policy.bundle.name) -DependencyPath @($Packages.FullName) -ForceApplicationShutdown
  $Package = Get-AppxPackage -Name Microsoft.DesktopAppInstaller
  if (-not $Package) { throw 'WinGet registration failed.' }
  $Command = Join-Path $Package.InstallLocation 'winget.exe'
  Invoke-Checked $Command @('--version')
  return $Command
}

if (@(Get-Installation).Count -ne 0) { throw 'Refusing to replace an existing Tauridium installation.' }
$Winget = $null
try {
  Set-Location -LiteralPath $Root
  Invoke-Checked $Python @('-c', "import sys; sys.path.insert(0, 'tools'); from security_tools import ensure_minisign; ensure_minisign()")
  foreach ($ReleaseVersion in @($PreviousVersion, $Version)) {
    $Lock = Join-Path $Root ('packaging/winget/releases/' + $ReleaseVersion + '.json')
    $Assets = Join-Path $RunRoot ('assets-' + $ReleaseVersion)
    $Manifest = Join-Path $RunRoot ('manifests/' + $ReleaseVersion)
    Invoke-Checked $Python @('tools/winget.py', 'fetch', '--lock', $Lock, '--assets-dir', $Assets)
    Invoke-Checked $Python @('tools/winget.py', 'prepare', '--lock', $Lock, '--assets-dir', $Assets, '--output', $Manifest)
  }
  $Winget = Get-WinGet
  Invoke-Checked $Winget @('settings', '--enable', 'LocalManifestFiles', '--disable-interactivity')
  foreach ($ReleaseVersion in @($PreviousVersion, $Version)) {
    Invoke-Checked $Winget @('validate', '--manifest', (Join-Path $RunRoot ('manifests/' + $ReleaseVersion)), '--disable-interactivity')
  }
  $Common = @('--architecture', $Architecture, '--scope', 'user', '--silent', '--accept-package-agreements', '--accept-source-agreements', '--disable-interactivity')
  Invoke-Checked $Winget (@('install', '--manifest', (Join-Path $RunRoot ('manifests/' + $PreviousVersion))) + $Common)
  Assert-Installation $PreviousVersion
  New-Item -ItemType Directory -Path $Profile | Out-Null
  $Marker = Join-Path $Profile 'winget-ci-persistence.marker'
  'retain synthetic data' | Set-Content -LiteralPath $Marker -Encoding utf8
  Invoke-Checked $Winget (@('upgrade', '--manifest', (Join-Path $RunRoot ('manifests/' + $Version))) + $Common)
  Assert-Installation $Version
  Invoke-Checked $Winget @('list', '--name', 'Tauridium', '--exact', '--accept-source-agreements', '--disable-interactivity')
  Invoke-Checked $Winget @('uninstall', '--name', 'Tauridium', '--exact', '--scope', 'user', '--silent', '--accept-source-agreements', '--disable-interactivity')
  if (@(Get-Installation).Count -ne 0 -or -not (Test-Path -LiteralPath $Marker)) { throw 'Uninstall did not preserve data or left ARP registration.' }
  Invoke-Checked $Winget (@('install', '--manifest', (Join-Path $RunRoot ('manifests/' + $Version))) + $Common)
  Assert-Installation $Version
  if ((Get-Content -LiteralPath $Marker -Raw).Trim() -ne 'retain synthetic data') { throw 'Reinstall modified application data.' }
  Write-Host ('WinGet native lifecycle passed on ' + $Architecture)
} finally {
  if ($Winget -and @(Get-Installation).Count -eq 1) {
    & $Winget uninstall --name Tauridium --exact --scope user --silent --accept-source-agreements --disable-interactivity
  }
  # This directory was absent at entry and holds only this disposable user's fixture.
  if (Test-Path -LiteralPath $Profile) { Remove-Item -LiteralPath $Profile -Recurse -Force }
}
