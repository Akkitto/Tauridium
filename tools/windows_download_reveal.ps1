# Called only by the fresh-host Windows GUI gate; uses synthetic files only.
function Test-Download-Reveal {
  $Fixture=Join-Path $Output 'synthetic-download'
  [IO.Directory]::CreateDirectory($Fixture) | Out-Null
  $Destination=Join-Path $Output ('tauridium-download-'+[Guid]::NewGuid().ToString('N'))
  [IO.Directory]::CreateDirectory($Destination) | Out-Null
  $Filename='download, % example.txt'
  $Expected=Join-Path $Destination $Filename
  $Payload='synthetic download contents'
  [IO.File]::WriteAllText((Join-Path $Fixture 'payload.bin'),$Payload,$Utf8)
  [IO.File]::WriteAllText((Join-Path $Fixture 'fixture.html'),
    ('<!doctype html><meta charset="utf-8"><h1>Download selection fixture</h1><a href="/payload.bin" download="'+$Filename+'">Download selection fixture file</a>'),$Utf8)
  $Listener=New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback,0)
  $Listener.Start(); $Port=$Listener.LocalEndpoint.Port; $Listener.Stop()
  $Server=Start-HttpFixtureServer -Python (Get-Command python.exe -ErrorAction Stop).Source -Directory $Fixture -Port $Port
  $Explorer=$null
  $Shell=$null
  try {
    Wait-HttpFixtureServer $Server
    $Services=@(@{id='download-fixture';name='Download fixture';recipeId='custom-website';isEnabled=$true;isLocalRecipe=$true;order=0;customUrl="http://127.0.0.1:$Port/fixture.html"})
    [IO.File]::WriteAllText((Join-Path $ProfileRoot 'local_profile.json'),(@{version=1;services=$Services;workspaces=@()} | ConvertTo-Json -Depth 6),$Utf8)
    $Config=Read-Settings
    foreach ($Entry in @{
      downloadToasts=$true; downloadToastDuration=0; downloadToastLocation='none';
      askEachDownload=$false; downloadDirectory=$Destination; preloadServices=$false;
      fetchMissingServiceIcons=$false; closeToSystemTray=$false
    }.GetEnumerator()) { $Config | Add-Member -NotePropertyName $Entry.Key -NotePropertyValue $Entry.Value -Force }
    [IO.File]::WriteAllText($Settings,($Config | ConvertTo-Json -Depth 12),$Utf8)
    Start-Tauridium
    Invoke-Control 'Download selection fixture file' ([Windows.Automation.ControlType]::Hyperlink)
    Wait-For { Test-Path -LiteralPath $Expected -PathType Leaf } 'actual native completed download'
    Check ([IO.File]::ReadAllText($Expected) -ceq $Payload) 'download payload is complete'
    Invoke-Control 'Show in folder'
    $FolderName=[IO.Path]::GetFileName($Destination)
    $ClassCondition=New-Object Windows.Automation.PropertyCondition([Windows.Automation.AutomationElement]::ClassNameProperty,'CabinetWClass')
    $Owned=@{ Window=$null }
    Wait-For {
      $FolderWindows=@([Windows.Automation.AutomationElement]::RootElement.FindAll([Windows.Automation.TreeScope]::Children,$ClassCondition) |
        Where-Object { $_.Current.Name.IndexOf($FolderName,[StringComparison]::Ordinal) -ge 0 })
      if ($FolderWindows.Count -gt 1) { throw 'Ambiguous fixture Explorer window.' }
      if ($FolderWindows.Count -eq 1) { $Owned.Window=$FolderWindows[0]; return $true }
      return $false
    } 'fixture-owned Explorer folder window'
    $Handle=[long]$Owned.Window.Current.NativeWindowHandle
    $Shell=New-Object -ComObject Shell.Application
    foreach ($Candidate in $Shell.Windows()) {
      # Inspect document/selection only after matching our synthetic folder HWND.
      if ([long]$Candidate.HWND -eq $Handle) { $Explorer=$Candidate; break }
    }
    Check ($null -ne $Explorer) 'fixture Explorer HWND matches the opened folder'
    Wait-For {
      $Selected=$Explorer.Document.SelectedItems()
      return $Selected.Count -eq 1 -and [string]$Selected.Item(0).Path -ceq $Expected
    } 'exact completed download selected in its parent'
    Check ([string]$Explorer.Document.Folder.Self.Path -ceq $Destination) 'Show in folder opens the parent directory'
    Check ([IO.File]::ReadAllText($Expected) -ceq $Payload) 'Show in folder preserves the downloaded file'
    $Explorer.Quit(); $Explorer=$null
    Activate-Tauridium
    Wait-For { $null -ne (Find-Control 'File shown in folder.') } 'reveal acknowledgement without dismissing the notification'
    Move-Item -LiteralPath $Expected -Destination (Join-Path $Destination 'moved.txt')
    Invoke-Control 'Show in folder'
    Wait-For { $null -ne (Find-Control 'This download is no longer at its saved location. It may have been moved or deleted.') } 'moved-file explanation'
    Check ($null -ne (Find-Control 'Show in folder')) 'moved-file failure retains the retry action'
    Invoke-Control 'Dismiss download notification'
    Wait-For { $null -eq (Find-Control 'Show in folder') } 'dismissed download action'
    Check $true 'completed downloads reveal safely and moved files remain dismissible'
    Stop-Tauridium
  } finally {
    try {
      if ($null -ne $Explorer) { $Explorer.Quit() }
      if ($script:Child -and -not $script:Child.HasExited) { Stop-Tauridium }
    } finally {
      if ($null -ne $Shell) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($Shell) }
      Stop-HttpFixtureServer $Server
    }
  }
}
