param(
  [Parameter(Mandatory = $true)]
  [string]$ScoopCore,

  [Parameter(Mandatory = $true)]
  [string]$Portable,

  [Parameter(Mandatory = $true)]
  [string]$Target,

  [Parameter(Mandatory = $true)]
  [string]$PreviousVersion
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ScoopCore = (Resolve-Path -LiteralPath $ScoopCore).Path
$Portable = (Resolve-Path -LiteralPath $Portable).Path
$PinnedScoopCommand = Join-Path $ScoopCore "bin\scoop.ps1"
if (-not (Test-Path -LiteralPath $PinnedScoopCommand -PathType Leaf)) {
  throw "Pinned Scoop command was not found: $PinnedScoopCommand"
}

$Version = (& node.exe -p "require('./src-tauri/tauri.conf.json').version").Trim()
if ([string]::IsNullOrWhiteSpace($Version)) {
  throw "Unable to resolve Tauridium version."
}

$RunRoot = Join-Path $env:RUNNER_TEMP "tauridium-scoop-$Target"
$ScoopRoot = Join-Path $RunRoot "scoop"
$ScoopCurrent = Join-Path $ScoopRoot "apps\scoop\current"
$ConfigRoot = Join-Path $RunRoot "config"
$ServeRoot = Split-Path -Parent $Portable
$ManifestPath = Join-Path $RunRoot "tauridium.json"
$AutoupdateManifestPath = Join-Path $RunRoot "tauridium-autoupdate.json"
$BucketName = "tauridium-ci"
$BucketRoot = Join-Path $ScoopRoot "buckets\$BucketName"
$BucketManifestDir = Join-Path $BucketRoot "bucket"
$BucketManifestPath = Join-Path $BucketManifestDir "tauridium.json"
$AppSpec = "$BucketName/tauridium"
$VersionPath = Join-Path $ServeRoot "scoop-version.txt"
$BuildInfoPath = Join-Path $RunRoot "build-info.json"
$DataDir = Join-Path $env:APPDATA "dev.brani.tauridium"
$PersistenceMarker = Join-Path $DataDir "scoop-ci-persistence.marker"
$Shortcut = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Scoop Apps\Tauridium.lnk"
$Server = $null

Remove-Item -LiteralPath $RunRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $ScoopCurrent -Force | Out-Null
Copy-Item -Path (Join-Path $ScoopCore "*") -Destination $ScoopCurrent -Recurse -Force
$ScoopCommand = Join-Path $ScoopCurrent "bin\scoop.ps1"
if (-not (Test-Path -LiteralPath $ScoopCommand -PathType Leaf)) {
  throw "Pinned Scoop core could not be staged in its normal installation layout."
}
New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
New-Item -ItemType Directory -Path $BucketManifestDir -Force | Out-Null

$env:SCOOP = $ScoopRoot
$env:SCOOP_CACHE = Join-Path $RunRoot "cache"
$env:XDG_CONFIG_HOME = $ConfigRoot
$env:SCOOP_NO_JUNCTIONS = "false"

try {
  $Listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
  $Listener.Start()
  $Port = ([System.Net.IPEndPoint]$Listener.LocalEndpoint).Port
  $Listener.Stop()

  $Python = (Get-Command -Name "python.exe" -ErrorAction Stop).Source
  $Server = Start-Process -FilePath $Python -ArgumentList @(
    "-m",
    "http.server",
    "$Port",
    "--bind",
    "127.0.0.1"
  ) -WorkingDirectory $ServeRoot -PassThru -WindowStyle Hidden
  Start-Sleep -Milliseconds 750

  $PortableName = Split-Path -Leaf $Portable
  $PortableUrl = "http://127.0.0.1:$Port/$PortableName"
  $PortableAutoupdateName = $PortableName.Replace($Version, '$version')
  $PortableAutoupdateUrl = "http://127.0.0.1:$Port/$PortableAutoupdateName"
  $CheckverUrl = "http://127.0.0.1:$Port/scoop-version.txt"
  $Version | Set-Content -LiteralPath $VersionPath -Encoding ascii -NoNewline

  & $Python tools/scoop.py local-manifest `
    --portable $Portable `
    --target $Target `
    --url $PortableUrl `
    --checkver-url $CheckverUrl `
    --autoupdate-url $PortableAutoupdateUrl `
    --output $ManifestPath
  if ($LASTEXITCODE -ne 0) {
    throw "Unable to generate local Scoop integration manifest."
  }

  $CurrentManifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
  $ScoopArchitecture = if ($Target -eq "x86_64-pc-windows-msvc") { "64bit" } else { "arm64" }

  # Exercise Scoop's own checkver/autoupdate implementation against a local release endpoint.
  $AutoupdateManifest = $CurrentManifest | ConvertTo-Json -Depth 20 | ConvertFrom-Json
  $AutoupdateManifest.version = $PreviousVersion
  $AutoupdateManifest | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $AutoupdateManifestPath -Encoding utf8NoBOM
  $CheckverCommand = Join-Path $ScoopCurrent "bin\checkver.ps1"
  & $CheckverCommand -App $AutoupdateManifestPath -Update -ThrowError
  if ($LASTEXITCODE -ne 0) {
    throw "Scoop checkver/autoupdate integration failed."
  }
  $UpdatedManifest = Get-Content -LiteralPath $AutoupdateManifestPath -Raw | ConvertFrom-Json
  if ($UpdatedManifest.version -ne $Version) {
    throw "Scoop autoupdate did not advance the manifest to Tauridium $Version."
  }
  $UpdatedArchitecture = $UpdatedManifest.architecture.$ScoopArchitecture
  $ExpectedArchitecture = $CurrentManifest.architecture.$ScoopArchitecture
  if ($UpdatedArchitecture.url -ne $ExpectedArchitecture.url) {
    throw "Scoop autoupdate produced an unexpected portable URL."
  }
  if ($UpdatedArchitecture.hash -ne $ExpectedArchitecture.hash) {
    throw "Scoop autoupdate produced an unexpected portable SHA-256."
  }

  $PreviousManifest = $CurrentManifest | ConvertTo-Json -Depth 20 | ConvertFrom-Json
  $PreviousManifest.version = $PreviousVersion
  $PreviousManifest | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $BucketManifestPath -Encoding utf8NoBOM

  # Install through a real isolated bucket, not a raw manifest path. This exercises the same
  # bucket/install.json lookup that Scoop uses for normal package updates from Extras.
  & $ScoopCommand install $AppSpec
  if ($LASTEXITCODE -ne 0) {
    throw "Scoop installation of the simulated previous Tauridium version failed."
  }
  $PreviousInstalledExe = Join-Path $ScoopRoot "apps\tauridium\$PreviousVersion\tauridium.exe"
  if (-not (Test-Path -LiteralPath $PreviousInstalledExe -PathType Leaf)) {
    throw "Scoop did not install the simulated previous Tauridium version through the local bucket."
  }
  $PreviousInstallInfoPath = Join-Path $ScoopRoot "apps\tauridium\$PreviousVersion\install.json"
  $PreviousInstallInfo = Get-Content -LiteralPath $PreviousInstallInfoPath -Raw | ConvertFrom-Json
  if ($PreviousInstallInfo.bucket -ne $BucketName) {
    throw "Scoop did not record the expected bucket identity for Tauridium."
  }

  if (-not (Test-Path -LiteralPath $Shortcut -PathType Leaf)) {
    throw "Scoop did not create the Tauridium Start Menu shortcut."
  }

  "persistent across Scoop replacement" | Set-Content -LiteralPath $PersistenceMarker -Encoding utf8NoBOM
  if ($PersistenceMarker.StartsWith($ScoopRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Tauridium application data must not live inside the Scoop installation root."
  }

  $CurrentManifest | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $BucketManifestPath -Encoding utf8NoBOM
  & $ScoopCommand update tauridium
  if ($LASTEXITCODE -ne 0) {
    throw "Scoop update to Tauridium $Version failed."
  }

  $InstalledExe = Join-Path $ScoopRoot "apps\tauridium\current\tauridium.exe"
  $InstalledVersionExe = Join-Path $ScoopRoot "apps\tauridium\$Version\tauridium.exe"
  if (-not (Test-Path -LiteralPath $InstalledExe -PathType Leaf)) {
    throw "Tauridium executable is missing after Scoop update."
  }
  if (-not (Test-Path -LiteralPath $InstalledVersionExe -PathType Leaf)) {
    throw "Scoop update did not install the current Tauridium version directory."
  }
  $InstallInfoPath = Join-Path $ScoopRoot "apps\tauridium\$Version\install.json"
  $InstallInfo = Get-Content -LiteralPath $InstallInfoPath -Raw | ConvertFrom-Json
  if ($InstallInfo.bucket -ne $BucketName) {
    throw "Scoop update did not retain the expected Tauridium bucket identity."
  }
  if (-not (Test-Path -LiteralPath $PersistenceMarker -PathType Leaf)) {
    throw "Tauridium application data did not survive Scoop update."
  }

  Remove-Item -LiteralPath $BuildInfoPath -Force -ErrorAction SilentlyContinue
  & $InstalledExe --build-info-file $BuildInfoPath
  if ($LASTEXITCODE -ne 0) {
    throw "Installed Tauridium build-info probe failed."
  }
  $BuildInfo = Get-Content -LiteralPath $BuildInfoPath -Raw | ConvertFrom-Json
  if ($BuildInfo.name -ne "Tauridium" -or $BuildInfo.version -ne $Version) {
    throw "Installed portable binary reports unexpected Tauridium identity."
  }
  if ($BuildInfo.buildMode -ne "production" -or $BuildInfo.target -ne $Target) {
    throw "Installed portable binary is not the expected production target."
  }

  & $ScoopCommand uninstall tauridium
  if ($LASTEXITCODE -ne 0) {
    throw "Scoop uninstall failed."
  }
  if (Test-Path -LiteralPath (Join-Path $ScoopRoot "apps\tauridium\current")) {
    throw "Scoop left Tauridium's current installation behind after uninstall."
  }
  if (-not (Test-Path -LiteralPath $PersistenceMarker -PathType Leaf)) {
    throw "External Tauridium application data was removed by Scoop uninstall."
  }

  & $ScoopCommand install $AppSpec
  if ($LASTEXITCODE -ne 0) {
    throw "Scoop reinstall failed."
  }
  if (-not (Test-Path -LiteralPath $PersistenceMarker -PathType Leaf)) {
    throw "External Tauridium application data did not survive Scoop reinstall."
  }
  if (-not (Test-Path -LiteralPath $Shortcut -PathType Leaf)) {
    throw "Tauridium shortcut is missing after Scoop reinstall."
  }

  & $ScoopCommand uninstall tauridium
  if ($LASTEXITCODE -ne 0) {
    throw "Final Scoop uninstall failed."
  }

  Write-Host "Scoop integration verified for Tauridium $Version ($Target)."
}
finally {
  if ($null -ne $Server -and -not $Server.HasExited) {
    Stop-Process -Id $Server.Id -Force -ErrorAction SilentlyContinue
  }
  Remove-Item -LiteralPath $PersistenceMarker -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $VersionPath -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $RunRoot -Recurse -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $Shortcut -Force -ErrorAction SilentlyContinue
}
