; Inno Setup script for the Clipnest installer.
; Build the app first (pyinstaller clipnest.spec -> dist\Clipnest\), then:
;   iscc installer\clipnest.iss        -> dist\Clipnest-Setup-<version>.exe

#define AppName "Clipnest"
#define AppVersion "1.2.0"
#define AppExe "Clipnest.exe"

[Setup]
; Never change AppId: Windows uses it to recognise upgrades of the same app.
AppId={{55FBB49D-2F2C-4295-BB0A-0991A4159E7D}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Vishnu VK
AppPublisherURL=https://github.com/vishnuvk2k/clipnest
AppCopyright=Copyright (c) 2026 Vishnu VK
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Ask "Install for me only" or "for all users" (the latter needs admin).
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
LicenseFile=license.txt
OutputDir=..\dist
OutputBaseFilename=Clipnest-Setup-{#AppVersion}
SetupIconFile=..\assets\clipnest.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
DisableWelcomePage=no
DisableDirPage=no
WizardImageFile=wizard-100.bmp,wizard-150.bmp,wizard-200.bmp
WizardSmallImageFile=wizard-small-100.bmp,wizard-small-150.bmp,wizard-small-200.bmp
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
CloseApplications=yes
VersionInfoVersion={#AppVersion}
VersionInfoDescription={#AppName} Setup

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\Clipnest\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; AppUserModelID matches the app's, so the taskbar shows the Clipnest icon and
; pinned shortcuts group with the running window.
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "Clipnest.App"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "Clipnest.App"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; The engine Clipnest downloaded on first launch. Settings and your downloaded
; files are kept.
Type: filesandordirs; Name: "{localappdata}\Clipnest\engine"

[Code]
// Before 1.1 the app was called Fetchly, with its own AppId. Carry its data
// over and remove it, so people don't end up with two apps.
const
  OldUninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{6F3C2A9E-5B1D-4C7E-9A2F-FE7C1B0D4A11}_is1';

function OldUninstaller(): String;
begin
  Result := '';
  if not RegQueryStringValue(HKCU, OldUninstallKey, 'UninstallString', Result) then
    RegQueryStringValue(HKLM, OldUninstallKey, 'UninstallString', Result);
  Result := RemoveQuotes(Result);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  OldData, NewData, Uninstaller: String;
  Code: Integer;
begin
  if CurStep <> ssInstall then
    exit;
  OldData := ExpandConstant('{localappdata}\Fetchly');
  NewData := ExpandConstant('{localappdata}\Clipnest');
  // Move settings, history and the downloaded engine before the old
  // uninstaller deletes the engine folder.
  if DirExists(OldData) and not DirExists(NewData) then
    RenameFile(OldData, NewData);
  Uninstaller := OldUninstaller();
  if (Uninstaller <> '') and FileExists(Uninstaller) then
    Exec(Uninstaller, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '', SW_HIDE,
         ewWaitUntilTerminated, Code);
end;
