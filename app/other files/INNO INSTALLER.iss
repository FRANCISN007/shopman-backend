; Script SHoMman App Installer
#define MyAppName "SHopMan App"
#define MyAppVersion "2.5"
#define MyAppPublisher "School of Accounting Package"
#define MyAppURL "https://www.example.com/"
#define MyAppExeName "python.exe"

[Setup]
PrivilegesRequired=admin
AppId={{7C26CBC0-0FD9-4943-9A21-2204ED49422F}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\PHONE_SHOP
DisableProgramGroupPage=yes
LicenseFile=C:\Users\KLOUNGE\Documents\PHONE_SHOP\license-shopman.txt
OutputDir=C:\Users\KLOUNGE\Desktop
OutputBaseFilename=PHONE_SHOP
SetupIconFile=C:\Users\KLOUNGE\Documents\PHONE_SHOP\shopman-inst.ico
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked  

[Files]
; Backend
Source: "C:\Users\KLOUNGE\Documents\PHONE_SHOP\app\*"; DestDir: "{app}\app"; Flags: ignoreversion recursesubdirs createallsubdirs

; ✅ Backup folder
Source: "C:\Users\KLOUNGE\Documents\PHONE_SHOP\backup\*"; DestDir: "{app}\backup"; Flags: ignoreversion recursesubdirs createallsubdirs

; ✅ React build only (no Node.js required)
Source: "C:\Users\KLOUNGE\Documents\PHONE_SHOP\react-frontend\build\*"; DestDir: "{app}\react-frontend\build"; Flags: ignoreversion recursesubdirs createallsubdirs


; Embedded Python
Source: "C:\Users\KLOUNGE\Documents\PHONE_SHOP\python-embed\*"; DestDir: "{app}\python"; Flags: ignoreversion recursesubdirs createallsubdirs

; Start script
Source: "C:\Users\KLOUNGE\Documents\PHONE_SHOP\start.py"; DestDir: "{app}"; Flags: ignoreversion

; Optional: .env file for backend
Source: "C:\Users\KLOUNGE\Documents\PHONE_SHOP\.env"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\python\python.exe"; Parameters: """{app}\start.py"""; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\python\python.exe"; Parameters: """{app}\start.py"""; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; ✅ Firewall rules for LAN access
Filename: "netsh"; Parameters: "advfirewall firewall add rule name=""HEMS-Backend"" dir=in action=allow protocol=TCP localport=8000"; Flags: runhidden
Filename: "netsh"; Parameters: "advfirewall firewall add rule name=""HEMS-Frontend"" dir=in action=allow protocol=TCP localport=3000"; Flags: runhidden

; ✅ Start backend
Filename: "{app}\python\{#MyAppExeName}"; Parameters: """{app}\start.py"""; WorkingDir: "{app}"; Flags: nowait
