param(
  [ValidateSet('x64','arm64')][Parameter(Mandatory=$true)][string]$Architecture,
  [string]$Version = '',
  [string]$PreviousVersion = ''
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Set-StrictMode -Version Latest
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') {
  throw 'Installer acceptance is restricted to disposable GitHub-hosted Windows runners.'
}
if ([Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant() -ne $Architecture) { throw 'Native Windows architecture mismatch.' }
$Root = Split-Path -Parent $PSScriptRoot
$Locks = Join-Path $Root 'packaging/chocolatey/releases'
$Versions = @(Get-ChildItem -LiteralPath $Locks -Filter '*.json' | ForEach-Object { [version]$_.BaseName } | Sort-Object -Descending)
if (-not $Version) { $Version = $Versions[0].ToString() }
if (-not $PreviousVersion) { $PreviousVersion = @($Versions | Where-Object { $_ -lt [version]$Version })[0].ToString() }
$RunRoot = Join-Path $env:RUNNER_TEMP ('tauridium-chocolatey-' + [guid]::NewGuid().ToString('N') + ' paths with spaces caf' + [char]0x00e9)
$Feed = Join-Path $RunRoot 'packages'
New-Item -ItemType Directory -Path $Feed -Force | Out-Null
$Python = (Get-Command python.exe -ErrorAction Stop).Source
$Choco = (Get-Command choco.exe -ErrorAction Stop).Source
$Profile = Join-Path $env:APPDATA 'dev.brani.tauridium'
$Diagnostics = Join-Path $env:LOCALAPPDATA 'Tauridium'
if ((Test-Path -LiteralPath $Profile) -or (Test-Path -LiteralPath $Diagnostics)) { throw 'Refusing existing application data.' }
. (Join-Path $Root 'packaging/chocolatey/tauridium.ps1')
if (@(Get-TauridiumRegistrations).Count -or @(Get-TauridiumProducts).Count) { throw 'Refusing an existing installation.' }
$ChocoData = Join-Path $env:ChocolateyInstall 'lib/tauridium'
if (Test-Path -LiteralPath $ChocoData) { throw 'Refusing an existing Chocolatey package.' }

function Invoke-TestCommand([string]$Command, [string[]]$Arguments, [bool]$Success=$true, [string]$ExpectedError='') {
  if (@($Arguments | Where-Object { $_ -match '["\r\n]' }).Count) { throw 'Unexpected harness argument.' }
  $Info = New-Object Diagnostics.ProcessStartInfo
  $Info.FileName = $Command
  # Windows Installer parses its switches itself. Quote values that need it,
  # retaining bare /i, /x and /qn switches, as in normal msiexec invocation.
  $Info.Arguments = (@($Arguments | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }) -join ' ')
  $Info.UseShellExecute = $false
  $Info.RedirectStandardOutput = $true
  $Info.RedirectStandardError = $true
  $Process = New-Object Diagnostics.Process
  $Process.StartInfo = $Info
  try {
    Write-Host ('Starting native test command: ' + [IO.Path]::GetFileName($Command))
    if (-not $Process.Start()) { throw 'Native command did not start.' }
    $Output = $Process.StandardOutput.ReadToEndAsync(); $Errors = $Process.StandardError.ReadToEndAsync()
    if (-not $Process.WaitForExit(240000)) { $Process.Kill(); throw ('Command timed out: ' + $Command) }
    if (-not $Output.Wait(15000) -or -not $Errors.Wait(15000)) { throw 'Native output did not close.' }
    Write-Host $Output.Result; Write-Host $Errors.Result
    Write-Host ('Native test exit: ' + [IO.Path]::GetFileName($Command) + ' = ' + $Process.ExitCode)
    $Okay = $Process.ExitCode -in @(0,3010)
    if ($Okay -ne $Success) { throw ('Unexpected command exit ' + $Process.ExitCode + ': ' + $Command) }
    if (-not $Success -and (-not $ExpectedError -or ($Output.Result + $Errors.Result) -notmatch [regex]::Escape($ExpectedError))) {
      throw 'Negative installer test failed for an unexpected reason.'
    }
  } finally { $Process.Dispose() }
}
function Invoke-Choco([string]$Verb, [string[]]$More=@(), [bool]$Success=$true, [string]$ExpectedError='') {
  Invoke-TestCommand $Choco (@($Verb,'tauridium','--yes','--no-progress','--limit-output','--source',$Feed) + $More) $Success $ExpectedError
}
function Assert-Installed([string]$Expected) {
  if (@(Get-Process -Name tauridium -ErrorAction SilentlyContinue).Count) { throw 'MSI unexpectedly launched Tauridium during unattended installation.' }
  $Products = @(Get-TauridiumProducts); Assert-TauridiumRegistrations $Products
  if ($Products.Count -ne 1 -or $Products[0].Version -ne $Expected) { throw 'Expected one exact machine-wide MSI installation.' }
  $Row = @(Get-TauridiumRegistrations)[0]
  $Base = if ($env:ProgramW6432) { $env:ProgramW6432 } else { $env:ProgramFiles }
  $script:InstalledExe = Join-Path $Base 'Tauridium/tauridium.exe'
  if (-not (Test-Path -LiteralPath $script:InstalledExe -PathType Leaf)) { throw 'Installed executable missing.' }
  $Probe = Join-Path $RunRoot ('build-info-' + [guid]::NewGuid().ToString('N') + '.json')
  Invoke-TestCommand $script:InstalledExe @('--build-info-file',$Probe)
  $Info = Get-Content -LiteralPath $Probe -Raw | ConvertFrom-Json
  $Target = if ($Architecture -eq 'x64') { 'x86_64-pc-windows-msvc' } else { 'aarch64-pc-windows-msvc' }
  if ($Info.version -ne $Expected -or $Info.target -ne $Target -or $Info.buildMode -ne 'production') { throw 'Actual installed binary identity mismatch.' }
}
function Assert-Removed {
  if (@(Get-TauridiumProducts).Count -or @(Get-TauridiumRegistrations).Count) { throw 'MSI registration remains after removal.' }
  if (Test-Path -LiteralPath $script:InstalledExe) { throw 'Installed executable remains after removal.' }
  if (-not (Test-Path -LiteralPath $script:Marker)) { throw 'Removal lost synthetic application data.' }
}
function Assert-PackageVersion([string]$Expected) {
  $Metadata = Join-Path $ChocoData 'tauridium.nuspec'
  [xml]$Document = Get-Content -LiteralPath $Metadata -Raw
  if ($Document.package.metadata.version -ne $Expected) { throw 'Chocolatey package tracking mismatch.' }
}
function Assert-GuiAndRunningGuard {
  $Process = Start-Process -FilePath $script:InstalledExe -ArgumentList '--startup-diagnostics' -PassThru
  try {
    $Deadline = [DateTime]::UtcNow.AddSeconds(60);$Ready=$false
    do {
      Start-Sleep -Milliseconds 500; $Process.Refresh()
      if ($Process.HasExited) { throw 'Installed GUI exited unexpectedly.' }
      $LogRoot = Join-Path $Diagnostics 'diagnostics'
      if (Test-Path -LiteralPath $LogRoot) {
        $Logs = @(Get-ChildItem -LiteralPath $LogRoot -Filter ('startup-*-' + $Process.Id + '.log'))
        if ($Logs.Count) { $Ready = (Get-Content -LiteralPath $Logs[0].FullName -Raw) -match 'event=tauri\.setup\.completed(?:\s|$)' }
      }
    } while ((-not $Ready -or $Process.MainWindowHandle -eq [IntPtr]::Zero) -and [DateTime]::UtcNow -lt $Deadline)
    if (-not $Ready -or -not $Process.Responding -or $Process.MainWindowHandle -eq [IntPtr]::Zero) { throw 'Installed GUI did not become ready and responsive.' }
    $Install = Join-Path $ChocoData 'tools/chocolateyInstall.ps1'
    Invoke-TestCommand 'powershell.exe' @('-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',$Install) $false 'Close all Tauridium windows'
    $Process.Refresh();if ($Process.HasExited) { throw 'Running-app refusal killed the application.' }
  } finally {
    # Only the synthetic process started by this harness may be stopped.
    if (-not $Process.HasExited) { $Process.Kill();$Process.WaitForExit() };$Process.Dispose()
  }
}

$Checks = New-Object 'Collections.Generic.List[string]'
$LifecycleFailed = $false
$FixtureKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Tauridium'
try {
  Invoke-TestCommand $Choco @('--version')
  foreach ($ReleaseVersion in @($PreviousVersion,$Version)) {
    $Assets = Join-Path $RunRoot ('assets-' + $ReleaseVersion)
    $Stage = Join-Path $RunRoot ('stage-' + $ReleaseVersion)
    $Lock = Join-Path $Locks ($ReleaseVersion + '.json')
    Invoke-TestCommand $Python @('tools/chocolatey.py','fetch','--lock',$Lock,'--assets-dir',$Assets)
    Invoke-TestCommand $Python @('tools/chocolatey.py','prepare','--lock',$Lock,'--assets-dir',$Assets,'--stage',$Stage)
    foreach ($Shell in @('powershell.exe','pwsh.exe')) {
      $Code = '$e=@();Get-ChildItem -LiteralPath ' + "'" + (Join-Path $Stage 'tools').Replace("'","''") + "'" + ' -Filter *.ps1 | ForEach-Object {$t=$null;$p=$null;[void][System.Management.Automation.Language.Parser]::ParseFile($_.FullName,[ref]$t,[ref]$p);$e+=$p};if($e.Count){throw $e}'
      Invoke-TestCommand $Shell @('-NoLogo','-NoProfile','-Command',$Code)
    }
    $Output = Join-Path $Feed ('tauridium.' + $ReleaseVersion + '.nupkg')
    # Repacking into the same exact output also proves byte reproducibility.
    1..2 | ForEach-Object { Invoke-TestCommand $Python @('tools/chocolatey.py','pack','--lock',$Lock,'--assets-dir',$Assets,'--stage',$Stage,'--output',$Output) }
  }
  $Checks.Add('Real choco pack, exact inventory and byte-identical repeat packaging for both releases')
  New-Item -Path $FixtureKey -Force | Out-Null
  New-ItemProperty -Path $FixtureKey -Name DisplayName -Value 'Tauridium' | Out-Null
  New-ItemProperty -Path $FixtureKey -Name Publisher -Value 'brani' | Out-Null
  Invoke-Choco 'install' @('--version',$PreviousVersion) $false 'A conflicting Tauridium installation exists'
  Remove-Item -LiteralPath $FixtureKey -Recurse
  if (@(Get-TauridiumProducts).Count) { throw 'Conflict refusal still installed an MSI.' }
  $Checks.Add('Conflicting per-user registration refused without installation')
  New-Item -ItemType Directory -Path $Profile | Out-Null
  $script:Marker = Join-Path $Profile 'chocolatey-synthetic-persistence.marker'
  [IO.File]::WriteAllText($script:Marker,'synthetic data kept through all MSI/Chocolatey operations')
  Invoke-Choco 'install' @('--version',$PreviousVersion)
  Assert-Installed $PreviousVersion;Assert-PackageVersion $PreviousVersion
  $Checks.Add('Previous release installed machine-wide with exact native production binary')
  # Model the actual MSI updater path independently of Chocolatey tracking.
  $Msi = Join-Path $RunRoot ('assets-' + $Version + '/tauridium-' + $Version + '-windows-' + $Architecture + '.msi')
  Invoke-TestCommand 'msiexec.exe' @('/i',$Msi,'/qn','/norestart','REBOOT=ReallySuppress')
  Assert-Installed $Version;Assert-PackageVersion $PreviousVersion
  $Checks.Add('Native MSI update preserves one product family while Chocolatey still records the previous version')
  Invoke-TestCommand 'powershell.exe' @('-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $RunRoot ('stage-' + $PreviousVersion + '/tools/chocolateyInstall.ps1'))) $false 'A newer Tauridium MSI is already installed'
  Assert-Installed $Version
  Invoke-Choco 'upgrade' @('--version',$Version)
  Assert-Installed $Version;Assert-PackageVersion $Version
  $Checks.Add('Chocolatey upgrade after native MSI update converges without downgrade or duplicates')
  Assert-GuiAndRunningGuard
  $Checks.Add('Responsive real production GUI and safe running-process refusal')
  Invoke-Choco 'install' @('--version',$Version,'--force','--install-arguments','ALLUSERS=2 MSIINSTALLPERUSER=1 AUTOLAUNCHAPP=1','--override-arguments')
  Assert-Installed $Version
  $Checks.Add('Explicit same-version reinstall preserves one machine installation even with caller scope overrides')
  Invoke-Choco 'uninstall'
  Assert-Removed
  Invoke-Choco 'install' @('--version',$Version)
  Assert-Installed $Version
  Invoke-Choco 'uninstall'
  Assert-Removed
  $Checks.Add('Uninstall/reinstall removes installed files and preserves synthetic application data')
  $Evidence = Join-Path $Root ('release/chocolatey/acceptance-' + $Architecture)
  New-Item -ItemType Directory -Path $Evidence -Force | Out-Null
  Copy-Item -Path (Join-Path $Feed '*.nupkg') -Destination $Evidence
  @{passed=$true;architecture=$Architecture;version=$Version;previousVersion=$PreviousVersion;checks=@($Checks);realPrivateAccountsUsed=$false} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $Evidence 'result.json') -Encoding UTF8
  Write-Host ('Chocolatey local lifecycle passed: ' + $Architecture)
 } catch {
  $LifecycleFailed = $true
  throw
} finally {
  try {
    if (Test-Path -LiteralPath $FixtureKey) { Remove-Item -LiteralPath $FixtureKey -Recurse -Force }
    # Only this disposable runner's newly created application may be removed.
    $Products = @(Get-TauridiumProducts)
    foreach ($Product in $Products) { Invoke-TestCommand 'msiexec.exe' @('/x',$Product.Code,'/qn','/norestart','REBOOT=ReallySuppress') }
  } catch {
    Write-Warning 'Disposable-runner MSI cleanup failed; the lifecycle remains unsuccessful. The original failure is preserved.'
    if (-not $LifecycleFailed) { throw }
  }
}
