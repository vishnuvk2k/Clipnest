; Inno Setup script for the Fetchly installer.
; Build the app first (pyinstaller fetchly.spec -> dist\Fetchly\), then:
;   iscc installer\fetchly.iss        -> dist\Fetchly-Setup-<version>.exe

#define AppName "Fetchly"
#define AppVersion "1.0.1"
#define AppExe "Fetchly.exe"

[Setup]
; Never change AppId: Windows uses it to recognise upgrades of the same app.
AppId={{6F3C2A9E-5B1D-4C7E-9A2F-FE7C1B0D4A11}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Fetchly contributors
AppPublisherURL=https://github.com/
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Ask "Install for me only" or "for all users" (the latter needs admin).
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
LicenseFile=license.txt
OutputDir=..\dist
OutputBaseFilename=Fetchly-Setup-{#AppVersion}
SetupIconFile=..\assets\fetchly.ico
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
Source: "..\dist\Fetchly\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; AppUserModelID matches the app's, so the taskbar shows the Fetchly icon and
; pinned shortcuts group with the running window.
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "Fetchly.App"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "Fetchly.App"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; The engine Fetchly downloaded on first launch. Settings and your downloaded
; files are kept.
Type: filesandordirs; Name: "{localappdata}\Fetchly\engine"
