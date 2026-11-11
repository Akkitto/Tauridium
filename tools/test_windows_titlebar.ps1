param([Parameter(Mandatory = $true)][string]$Binary, [string]$Output = "release/evidence/windows-titlebar")
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') { throw 'This GUI gate requires a fresh GitHub-hosted Windows CI user profile.' }
$Binary = (Resolve-Path -LiteralPath $Binary).Path
$ProfileRoot = Join-Path ([Environment]::GetFolderPath('ApplicationData')) 'dev.brani.tauridium'
if (Test-Path -LiteralPath $ProfileRoot) { throw 'Existing Tauridium data found; refusing to inspect or change it.' }
if (Get-Process -Name tauridium -ErrorAction SilentlyContinue) { throw 'An existing Tauridium process is running.' }
$Output = [IO.Path]::GetFullPath($Output)
[IO.Directory]::CreateDirectory($Output) | Out-Null
[IO.Directory]::CreateDirectory($ProfileRoot) | Out-Null
$Settings = Join-Path $ProfileRoot 'app_settings.json'
$Utf8 = New-Object Text.UTF8Encoding($false)
# Missing unifiedTitleBar exercises migration from an older profile.
[IO.File]::WriteAllText($Settings, '{"closeToSystemTray":false,"theme":"dark"}', $Utf8)
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class ChromeNative {
  [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left, Top, Right, Bottom; }
  [StructLayout(LayoutKind.Sequential)] public struct Point { public int X, Y; }
  [StructLayout(LayoutKind.Sequential)] public struct TitleInfo {
    public int Size; public Rect Bar;
    [MarshalAs(UnmanagedType.ByValArray, SizeConst=6)] public uint[] State;
    [MarshalAs(UnmanagedType.ByValArray, SizeConst=6)] public Rect[] Buttons;
  }
  [DllImport("user32.dll")] public static extern IntPtr GetMenu(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h,out Rect r);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h,int n);
  [DllImport("user32.dll")] public static extern bool IsZoomed(IntPtr h);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
  [DllImport("user32.dll")] public static extern uint GetDpiForWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(Point p);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] private static extern IntPtr FindWindowEx(IntPtr p,IntPtr a,string c,string n);
  [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr h,out uint pid);
  [DllImport("user32.dll", EntryPoint="SendMessageW")] public static extern IntPtr SendMessage(IntPtr h,uint m,IntPtr w,IntPtr l);
  [DllImport("user32.dll", EntryPoint="SendMessageW")] private static extern IntPtr TitleMessage(IntPtr h,uint m,IntPtr w,ref TitleInfo info);
  [DllImport("user32.dll")] public static extern bool PostMessageW(IntPtr h,uint m,IntPtr w,IntPtr l);
  public static TitleInfo Title(IntPtr h) {
    TitleInfo t=new TitleInfo(); t.Size=Marshal.SizeOf(typeof(TitleInfo)); t.State=new uint[6]; t.Buttons=new Rect[6];
    TitleMessage(h,0x033f,IntPtr.Zero,ref t); return t;
  }
  public static int Hit(IntPtr h,Point p) { return (int)SendMessage(h,0x84,IntPtr.Zero,new IntPtr(((p.Y&65535)<<16)|(p.X&65535))); }
  public static bool HasPopup(int pid) {
    IntPtr h=IntPtr.Zero;
    while ((h=FindWindowEx(IntPtr.Zero,h,"#32768",null)) != IntPtr.Zero) {
      uint owner; GetWindowThreadProcessId(h,out owner); if (owner==(uint)pid) return true;
    } return false;
  }
}
'@
$script:Child = $null
$script:Window = [IntPtr]::Zero
$script:Checks = New-Object 'System.Collections.Generic.List[string]'
function Wait-For([scriptblock]$Condition, [string]$Label, [int]$Seconds = 45) {
  $Deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
  do {
    if (& $Condition) { return }
    if ($script:Child -and $script:Child.HasExited) { throw "Tauridium exited while waiting for $Label" }
    Start-Sleep -Milliseconds 150
  } while ([DateTime]::UtcNow -lt $Deadline)
  throw "Timed out waiting for $Label"
}
function Check([bool]$Passed, [string]$Label) {
  if (-not $Passed) { throw "Failed: $Label" }
  $script:Checks.Add($Label); Write-Host "PASS $Label"
}
function Root { return [Windows.Automation.AutomationElement]::FromHandle($script:Window) }
function Find-Control([string]$Name, [Windows.Automation.ControlType]$Type = $null) {
  $Condition = New-Object Windows.Automation.PropertyCondition([Windows.Automation.AutomationElement]::NameProperty,$Name)
  if ($null -ne $Type) {
    $Kind = New-Object Windows.Automation.PropertyCondition([Windows.Automation.AutomationElement]::ControlTypeProperty,$Type)
    $Condition = New-Object Windows.Automation.AndCondition($Condition,$Kind)
  }
  return (Root).FindFirst([Windows.Automation.TreeScope]::Descendants,$Condition)
}
function Invoke-Control([string]$Name, [Windows.Automation.ControlType]$Type = [Windows.Automation.ControlType]::Button) {
  Wait-For { $null -ne (Find-Control $Name $Type) } $Name
  $Pattern = (Find-Control $Name $Type).GetCurrentPattern([Windows.Automation.InvokePattern]::Pattern)
  $Pattern.Invoke()
}
function Start-Tauridium {
  $script:Child = Start-Process -FilePath $Binary -PassThru
  Wait-For { $script:Child.Refresh(); $script:Child.MainWindowHandle -ne [IntPtr]::Zero } 'main window'
  $script:Window = $script:Child.MainWindowHandle
  [ChromeNative]::SetForegroundWindow($script:Window) | Out-Null
  Wait-For { $null -ne (Find-Control 'Application' ([Windows.Automation.ControlType]::MenuBar)) -or [ChromeNative]::GetMenu($script:Window) -ne [IntPtr]::Zero } 'application menus'
}
function Stop-Tauridium {
  [ChromeNative]::PostMessageW($script:Window,0x10,[IntPtr]::Zero,[IntPtr]::Zero) | Out-Null
  if (-not $script:Child.WaitForExit(15000)) { throw 'Normal application close did not exit.' }
  $script:Child.Dispose(); $script:Child = $null
}
function Check-Caption {
  Wait-For { ([ChromeNative]::Title($script:Window)).Buttons[3].Right -gt ([ChromeNative]::Title($script:Window)).Buttons[3].Left } 'native caption buttons'
  $Info = [ChromeNative]::Title($script:Window)
  foreach ($Entry in @(@(2,8,'minimize'),@(3,9,'maximize'),@(5,20,'close'))) {
    $R = $Info.Buttons[$Entry[0]]
    Check ($R.Right -gt $R.Left -and $R.Bottom -gt $R.Top) "native $($Entry[2]) rectangle exists"
    $P = New-Object ChromeNative+Point
    $P.X = [int](($R.Left+$R.Right)/2); $P.Y = [int](($R.Top+$R.Bottom)/2)
    Check ([ChromeNative]::WindowFromPoint($P) -eq $script:Window) "native $($Entry[2]) is not covered by a WebView"
    Check ([ChromeNative]::Hit($script:Window,$P) -eq $Entry[1]) "native $($Entry[2]) hit test"
  }
}
function Outer-Size {
  $R = New-Object ChromeNative+Rect
  if (-not [ChromeNative]::GetWindowRect($script:Window,[ref]$R)) { throw 'Unable to read the test window rectangle.' }
  return @($R.Right-$R.Left,$R.Bottom-$R.Top)
}
function Open-Advanced {
  [ChromeNative]::SetForegroundWindow($script:Window) | Out-Null
  [Windows.Forms.SendKeys]::SendWait('^,')
  Invoke-Control 'Advanced'
  Wait-For { $null -ne (Find-Control 'Unified title bar' ([Windows.Automation.ControlType]::CheckBox)) } 'title-bar setting'
}
function Read-Settings([string]$Path = $Settings) {
  $Stream = [IO.File]::Open($Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,([IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete))
  $Reader = New-Object IO.StreamReader($Stream)
  try { return ($Reader.ReadToEnd() | ConvertFrom-Json) } finally { $Reader.Dispose() }
}
function Toggle-Chrome([bool]$Enabled) {
  $Toggle = (Find-Control 'Unified title bar' ([Windows.Automation.ControlType]::CheckBox)).GetCurrentPattern([Windows.Automation.TogglePattern]::Pattern)
  $Expected = if ($Enabled) { [Windows.Automation.ToggleState]::On } else { [Windows.Automation.ToggleState]::Off }
  if ($Toggle.Current.ToggleState -ne $Expected) { $Toggle.Toggle() }
  Wait-For { $Value=Read-Settings; $Value.PSObject.Properties['unifiedTitleBar'] -and $Value.unifiedTitleBar -is [bool] -and $Value.unifiedTitleBar -eq $Enabled } 'saved title-bar preference'
}
try {
  Start-Tauridium
  Check ([ChromeNative]::GetMenu($script:Window) -eq [IntPtr]::Zero) 'older settings default to a unified title bar'
  Check-Caption
  $OriginalOuter = Outer-Size
  Check ($null -ne (Find-Control 'Application' ([Windows.Automation.ControlType]::MenuBar))) 'accessible application menu bar exists'
  Invoke-Control 'Tauridium' ([Windows.Automation.ControlType]::MenuItem)
  Wait-For { [ChromeNative]::HasPopup($script:Child.Id) } 'native application popup'
  Check $true 'unified menu opens a real native popup'
  [Windows.Forms.SendKeys]::SendWait('{ESC}')
  Wait-For { -not [ChromeNative]::HasPopup($script:Child.Id) } 'dismissed native popup'
  Invoke-Control 'Use Tauridium without an account'
  Open-Advanced
  Check ((Find-Control 'Unified title bar' ([Windows.Automation.ControlType]::CheckBox)).Current.BoundingRectangle.Width -le 48) 'Advanced toggle has bounded switch geometry'
  Toggle-Chrome $false
  Check ([ChromeNative]::GetMenu($script:Window) -eq [IntPtr]::Zero) 'saved classic preference does not reconstruct a live window'
  Stop-Tauridium
  $SavedWindow = (Read-Settings (Join-Path $ProfileRoot 'window-state.json')).main
  Check ($SavedWindow.outer_size -eq $true -and $SavedWindow.width -eq $OriginalOuter[0] -and $SavedWindow.height -eq $OriginalOuter[1]) 'physical outer size is stored with an explicit format marker'
  Start-Tauridium
  Check ([ChromeNative]::GetMenu($script:Window) -ne [IntPtr]::Zero) 'restart restores the classic native menu bar'
  $RestoredOuter = Outer-Size
  Check ($RestoredOuter[0] -eq $OriginalOuter[0] -and $RestoredOuter[1] -eq $OriginalOuter[1]) 'classic restart preserves outside dimensions'
  Check-Caption
  Open-Advanced
  Toggle-Chrome $true
  Check ([ChromeNative]::GetMenu($script:Window) -ne [IntPtr]::Zero) 'saved unified preference waits for restart'
  Stop-Tauridium
  Start-Tauridium
  Check ([ChromeNative]::GetMenu($script:Window) -eq [IntPtr]::Zero) 'restart restores unified chrome'
  $RestoredOuter = Outer-Size
  Check ($RestoredOuter[0] -eq $OriginalOuter[0] -and $RestoredOuter[1] -eq $OriginalOuter[1]) 'unified restart preserves outside dimensions'
  Check-Caption
  [ChromeNative]::ShowWindow($script:Window,3) | Out-Null
  Wait-For { [ChromeNative]::IsZoomed($script:Window) } 'maximized window'
  Check-Caption
  [ChromeNative]::ShowWindow($script:Window,9) | Out-Null
  Wait-For { -not [ChromeNative]::IsZoomed($script:Window) } 'restored window'
  [ChromeNative]::ShowWindow($script:Window,6) | Out-Null
  Wait-For { [ChromeNative]::IsIconic($script:Window) } 'minimized window'
  [ChromeNative]::ShowWindow($script:Window,9) | Out-Null
  Wait-For { -not [ChromeNative]::IsIconic($script:Window) } 'restored minimized window'
  Check-Caption
  [ChromeNative]::SetForegroundWindow($script:Window) | Out-Null
  Wait-For { [ChromeNative]::GetForegroundWindow() -eq $script:Window } 'foreground test window'
  [Windows.Forms.SendKeys]::SendWait('{F10}')
  Wait-For { [Windows.Automation.AutomationElement]::FocusedElement.Current.Name -eq 'Tauridium' } 'F10 menu access'
  [Windows.Forms.SendKeys]::SendWait('{RIGHT}')
  Wait-For { [Windows.Automation.AutomationElement]::FocusedElement.Current.Name -eq 'Edit' } 'menu arrow navigation'
  [Windows.Forms.SendKeys]::SendWait('{ESC}')
  Check $true 'F10 and arrow navigation are accessible'
  Stop-Tauridium
  Start-Tauridium
  $RestoredOuter = Outer-Size
  Check ($RestoredOuter[0] -eq $OriginalOuter[0] -and $RestoredOuter[1] -eq $OriginalOuter[1]) 'repeated unified restart does not accumulate frame height'
  [ChromeNative]::ShowWindow($script:Window,3) | Out-Null
  Wait-For { [ChromeNative]::IsZoomed($script:Window) } 'maximized state before restart'
  Stop-Tauridium
  Start-Tauridium
  Wait-For { [ChromeNative]::IsZoomed($script:Window) } 'restored maximized state'
  Check-Caption
  [ChromeNative]::ShowWindow($script:Window,9) | Out-Null
  Wait-For { -not [ChromeNative]::IsZoomed($script:Window) } 'normal window after maximized restart'
  $RestoredOuter = Outer-Size
  Check ($RestoredOuter[0] -eq $OriginalOuter[0] -and $RestoredOuter[1] -eq $OriginalOuter[1]) 'maximized restart preserves normal outside dimensions'
  Stop-Tauridium
  $Result = @{ passed=$true; checks=$script:Checks.ToArray(); privateAccountsUsed=$false; titleBarModes=@('unified-default','classic-restarted','unified-restarted') }
  [IO.File]::WriteAllText((Join-Path $Output 'result.json'),($Result | ConvertTo-Json -Depth 6),$Utf8)
  Write-Host 'Native production Windows title-bar smoke passed.'
} finally {
  if ($script:Child -and -not $script:Child.HasExited) {
    [ChromeNative]::PostMessageW($script:Window,0x10,[IntPtr]::Zero,[IntPtr]::Zero) | Out-Null
    if (-not $script:Child.WaitForExit(5000)) { Stop-Process -Id $script:Child.Id -Force }
  }
}
