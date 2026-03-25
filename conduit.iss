; =============================================================================
; Conduit — Windows Installer (Inno Setup)
; =============================================================================
; Build manually:
;   iscc conduit.iss
;
; Build with a version number:
;   iscc /DMyAppVersion=1.0.0 conduit.iss
;
; Requires Inno Setup 6: https://jrsoftware.org/isdl.php
; =============================================================================

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

#define MyAppName      "Conduit"
#define MyAppPublisher "Kerrick Shaw-Vincent"
#define MyAppURL       "https://github.com/BingleP/conduit"

[Setup]
AppId={{7F3A2E1D-B4C5-4F89-A012-3456789ABCDE}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=conduit-{#MyAppVersion}-setup
SetupIconFile=frontend\icons\conduit.ico
WizardSmallImageFile=frontend\icons\conduit-48.png
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\frontend\icons\conduit.ico
MinVersion=10.0
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Python source
Source: "desktop.py";    DestDir: "{app}"; Flags: ignoreversion
Source: "main.py";       DestDir: "{app}"; Flags: ignoreversion
Source: "encoder.py";    DestDir: "{app}"; Flags: ignoreversion
Source: "database.py";   DestDir: "{app}"; Flags: ignoreversion
Source: "scanner.py";    DestDir: "{app}"; Flags: ignoreversion
Source: "requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "install.ps1";   DestDir: "{app}"; Flags: ignoreversion
Source: "conduit.bat";   DestDir: "{app}"; Flags: ignoreversion
; Frontend (all files including icons)
Source: "frontend\*"; DestDir: "{app}\frontend"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}";                     Filename: "{app}\conduit.bat"; IconFilename: "{app}\frontend\icons\conduit.ico"; WorkingDir: "{app}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#MyAppName}";             Filename: "{app}\conduit.bat"; IconFilename: "{app}\frontend\icons\conduit.ico"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\install.ps1"" -NoShortcut"; \
  WorkingDir: "{app}"; \
  StatusMsg: "Setting up Python environment (this may take a minute)..."; \
  Flags: runhidden waituntilterminated

[Code]
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
  PythonOk: Boolean;
begin
  Result := True;
  PythonOk := False;

  // Check via 'python'
  if Exec('powershell.exe',
    '-NoProfile -Command "python -c ''import sys; exit(0 if sys.version_info >= (3,10) else 1)''"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    if ResultCode = 0 then PythonOk := True;
  end;

  // Check via 'py' launcher
  if not PythonOk then
  begin
    if Exec('powershell.exe',
      '-NoProfile -Command "py -3 -c ''import sys; exit(0 if sys.version_info >= (3,10) else 1)''"',
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    begin
      if ResultCode = 0 then PythonOk := True;
    end;
  end;

  if not PythonOk then
  begin
    if MsgBox(
      'Python 3.10 or later was not found on this system.' + #13#10#13#10 +
      'Conduit requires Python 3.10+. Download it from:' + #13#10 +
      'https://python.org/downloads' + #13#10#13#10 +
      'During installation, check "Add Python to PATH".' + #13#10#13#10 +
      'Continue installing anyway?',
      mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := False;
    end;
  end;
end;
