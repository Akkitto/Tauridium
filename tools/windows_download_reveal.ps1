# A reveal is a desktop activation request; exercise genuine user input.
function Click-Download-Reveal {
  Activate-Tauridium
  $Click=@{ Point=$null }
  Wait-For {
    $Button=Find-Control 'Show in folder' ([Windows.Automation.ControlType]::Button)
    if (-not $Button -or $Button.Current.IsOffscreen -or -not $Button.Current.IsEnabled) { return $false }
    $Bounds=$Button.Current.BoundingRectangle
    if ($Bounds.IsEmpty -or $Bounds.Width -le 0 -or $Bounds.Height -le 0) { return $false }
    foreach ($Value in @($Bounds.Left,$Bounds.Top,$Bounds.Width,$Bounds.Height)) {
      if ([Double]::IsNaN($Value) -or [Double]::IsInfinity($Value)) { return $false }
    }
    $Point=New-Object ChromeNative+Point
    $Point.X=[int]($Bounds.Left+$Bounds.Width/2); $Point.Y=[int]($Bounds.Top+$Bounds.Height/2)
    if (-not [ChromeNative]::OwnsPoint($script:Window,$Point)) { return $false }
    $Click.Point=$Point
    return $true
  } 'uncovered native download reveal button'
  [ChromeNative]::ClickPoint($script:Window,$Click.Point.X,$Click.Point.Y,$false)
}

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
    # Keep the intended download between decoys for name, size and date sorts.
    # Opening a folder or selecting its first item cannot satisfy this check.
    $Older=Join-Path $Destination '000-unselected.txt'
    $Newer=Join-Path $Destination 'zzz-unselected.txt'
    [IO.File]::WriteAllText($Older,'0',$Utf8)
    [IO.File]::WriteAllText($Newer,('x'*4096),$Utf8)
    $SavedAt=[IO.File]::GetLastWriteTimeUtc($Expected)
    [IO.File]::SetLastWriteTimeUtc($Older,$SavedAt.AddHours(-1))
    [IO.File]::SetLastWriteTimeUtc($Newer,$SavedAt.AddHours(1))
    Click-Download-Reveal
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
    # Make the owned file-manager view observable without selecting any item.
    [ChromeNative]::ShowWindow([IntPtr]$Handle,9) | Out-Null
    [ChromeNative]::SetForegroundWindow([IntPtr]$Handle) | Out-Null
    Wait-For { [ChromeNative]::GetForegroundWindow() -eq [IntPtr]$Handle } 'foreground fixture Explorer window'
    $Shell=New-Object -ComObject Shell.Application
    # Windows 11 can expose several tab documents for one Explorer HWND.
    # Bind the synthetic folder document as well as its window before reading
    # its selection. Windows filesystem paths compare without case sensitivity.
    $Selection=@{ Explorer=$null; Documents=0; FolderMatches=0; Count=-1; ExactCase=$false }
    try {
      Wait-For {
        $Selection.Documents=0; $Selection.FolderMatches=0; $Selection.Count=-1
        foreach ($Candidate in $Shell.Windows()) {
          if ([long]$Candidate.HWND -ne $Handle) { continue }
          $Selection.Documents++
          $Document=$Candidate.Document
          if ($null -eq $Document -or $null -eq $Document.Folder) { continue }
          if (-not [string]::Equals([string]$Document.Folder.Self.Path,$Destination,[StringComparison]::OrdinalIgnoreCase)) { continue }
          $Selection.FolderMatches++
          $Selection.Explorer=$Candidate
          $Selected=$Document.SelectedItems()
          $Selection.Count=$Selected.Count
          if ($Selected.Count -ne 1) { continue }
          $SelectedPath=[string]$Selected.Item(0).Path
          $Selection.ExactCase=[string]::Equals($SelectedPath,$Expected,[StringComparison]::Ordinal)
          if ([string]::Equals($SelectedPath,$Expected,[StringComparison]::OrdinalIgnoreCase)) { return $true }
        }
        return $false
      } 'exact completed download selected in its parent'
    } finally {
      # Read-only UIA cross-check if legacy Shell automation reports no selection.
      # Restrict lookup to our unique fixture window and known synthetic filename.
      $AccessibleSelected=$false
      $AccessibleStatus='available'
      try {
        $FullName=New-Object Windows.Automation.PropertyCondition([Windows.Automation.AutomationElement]::NameProperty,$Filename)
        $ShortName=New-Object Windows.Automation.PropertyCondition([Windows.Automation.AutomationElement]::NameProperty,([IO.Path]::GetFileNameWithoutExtension($Filename)))
        $KnownName=New-Object Windows.Automation.OrCondition($FullName,$ShortName)
        foreach ($Node in $Owned.Window.FindAll([Windows.Automation.TreeScope]::Descendants,$KnownName)) {
          $Item=$Node
          for ($Depth=0; $Depth -lt 5 -and $null -ne $Item; $Depth++) {
            $Pattern=$null
            if ($Item.TryGetCurrentPattern([Windows.Automation.SelectionItemPattern]::Pattern,[ref]$Pattern)) {
              if ($Pattern.Current.IsSelected -and -not $Item.Current.IsOffscreen) { $AccessibleSelected=$true }
              break
            }
            $Item=[Windows.Automation.TreeWalker]::ControlViewWalker.GetParent($Item)
          }
        }
      } catch [Windows.Automation.ElementNotAvailableException] { $AccessibleStatus='unavailable' }
      Write-Host ('Fixture accessibility metadata: knownFileSelected={0}; status={1}; foreground={2}' -f $AccessibleSelected,$AccessibleStatus,([ChromeNative]::GetForegroundWindow() -eq [IntPtr]$Handle))
      Write-Host ('Fixture selection metadata: documents={0}; matchingFolders={1}; selectedCount={2}; exactPathCase={3}' -f $Selection.Documents,$Selection.FolderMatches,$Selection.Count,$Selection.ExactCase)
      $Explorer=$Selection.Explorer
    }
    Check ($null -ne $Explorer) 'fixture Explorer HWND and document match the opened folder'
    Check ([string]::Equals([string]$Explorer.Document.Folder.Self.Path,$Destination,[StringComparison]::OrdinalIgnoreCase)) 'Show in folder opens the parent directory'
    Check ([IO.File]::ReadAllText($Expected) -ceq $Payload) 'Show in folder preserves the downloaded file'
    $Explorer.Quit(); $Explorer=$null
    Activate-Tauridium
    Wait-For { $null -ne (Find-Control 'File shown in folder.') } 'reveal acknowledgement without dismissing the notification'
    Move-Item -LiteralPath $Expected -Destination (Join-Path $Destination 'moved.txt')
    Click-Download-Reveal
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
