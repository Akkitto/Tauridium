$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'tauridium.ps1')
Assert-TauridiumInstallerArguments
Assert-TauridiumStopped
# The upgrade family survives a legitimate MSI self-update that changes ProductCode.
$Products = @(Get-TauridiumProducts)
Assert-TauridiumRegistrations $Products
foreach ($Product in $Products) {
  Uninstall-ChocolateyPackage -PackageName 'tauridium' -FileType 'msi' `
    -SilentArgs ($Product.Code + ' /qn /norestart REBOOT=ReallySuppress') -ValidExitCodes @(0, 1605, 1614, 3010)
}
if (@(Get-TauridiumProducts).Count -ne 0) { throw 'Tauridium MSI removal did not complete.' }
# Deliberately leave application profiles, sessions, backups and shared WebView2 alone.
