; VETMO Admin — установщик админ-версии (Inno Setup 6.7+).
; Сборка: ISCC.exe /DMyAppVersion=0.2.0 installer\VETMO-Admin.iss
; Требуется готовый dist\VETMO-Admin.exe (PyInstaller, см. vetmo-admin.spec).
;
; Admin — инструмент сопровождения: он читает service_role и STRATZ-токен из
; %APPDATA%\VETMO\secrets.env. Установщик секреты НЕ создаёт и не копирует.

#ifndef MyAppVersion
  #define MyAppVersion "0.2.0"
#endif

#define MyAppName "VETMO Admin"
#define MyAppExeName "VETMO-Admin.exe"
#define MyAppPublisher "VETMO"
#define MyAppId "{{B7C1E5A4-6D2B-4F8C-9E31-2A5D8F0C7B14}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\VETMO Admin
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Admin ставится в профиль пользователя: те же права, что и у VETMO.
PrivilegesRequired=lowest
OutputDir=..\release
OutputBaseFilename=VETMO-Admin-Setup-{#MyAppVersion}
SetupIconFile=..\vetmo_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
CloseApplicationsFilter={#MyAppExeName}
RestartApplications=no
AllowNoIcons=yes
; Установщик не подписан: Windows SmartScreen может показать предупреждение.
; Для публичного релиза подпишите Setup и VETMO-Admin.exe сертификатом Authenticode.

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Dirs]
; Каталог для secrets.env и логов: создаётся пустым, секреты заполняет оператор.
Name: "{userappdata}\VETMO"

[Files]
Source: "..\dist\VETMO-Admin.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "ADMIN-SETUP.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent unchecked
