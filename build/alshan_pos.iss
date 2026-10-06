; ===========================================================================
;  ALSHAN POS SYSTEM - Inno Setup script
;
;  Build order (handled by build\build.bat):
;    1. PyInstaller produces ..\dist\ALSHAN_POS_SYSTEM\
;    2. ISCC.exe compiles this script into Setup_ALSHAN_POS_SYSTEM_1.0.0.exe
;
;  The installer needs NO Python, NO SQLite and NO administrator rights:
;  the program is installed per user and keeps its data in %LOCALAPPDATA%.
; ===========================================================================

#define MyAppName "ALSHAN POS SYSTEM"
#define MyAppExeName "ALSHAN_POS_SYSTEM.exe"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Alshan Software"
#define MyAppURL "https://alshansoftware.example"
#define SourceDir "..\dist\ALSHAN_POS_SYSTEM"

[Setup]
AppId={{7C3F1B52-4E6A-4E29-9A1B-8F2C4D6E1A01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} installer
DefaultDirName={localappdata}\Programs\AlshanPOS
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=.
OutputBaseFilename=Setup_ALSHAN_POS_SYSTEM_v{#MyAppVersion}
SetupIconFile=..\assets\alshan_pos.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
DisableWelcomePage=no
CloseApplications=yes
RestartApplications=no
ArchitecturesInstallIn64BitMode=x64
MinVersion=10.0
LicenseFile=..\LICENSE
ChangesAssociations=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.1

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
    Tasks: desktopicon
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppName}"; \
    Filename: "{app}\{#MyAppExeName}"; Tasks: quicklaunchicon

[Run]
Filename: "{app}\{#MyAppExeName}"; \
    Description: "Launch {#MyAppName}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; The database, backups, logs and receipts live outside the program folder and
; are deliberately kept so that a reinstall never loses the shop's history.
Type: files; Name: "{app}\*.log"

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
end;

function InitializeUninstall(): Boolean;
begin
  Result := MsgBox('Uninstall {#MyAppName}?'#13#10#13#10 +
    'Your sales history, products and backups will NOT be deleted - they stay in:'#13#10 +
    '  %LOCALAPPDATA%\AlshanPOS' + #13#10#13#10 +
    'Remove the program files only?', mbConfirmation, MB_YESNO) = IDYES;
end;
