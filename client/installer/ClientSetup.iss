; Inno Setup script for packaging the Windows client together with config and
; helper scripts. The service installation step is optional and delegated to
; the executable switch implemented in Client.cpp.

[Setup]
AppName=Work Activity Monitor Client
AppVersion=2.0.0
DefaultDirName={autopf}\WorkActivityMonitor
DefaultGroupName=Work Activity Monitor
OutputDir=.
OutputBaseFilename=WorkActivityMonitorClientSetup
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64

[Files]
Source: "..\build\Release\Client.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\config.ini"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\install_service.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\uninstall_service.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Work Activity Monitor Client"; Filename: "{app}\Client.exe"

[Tasks]
Name: "installservice"; Description: "Install Windows Service"; Flags: unchecked

[Run]
Filename: "{app}\Client.exe"; Parameters: "--install-service"; Description: "Install Windows Service"; Flags: runhidden waituntilterminated; Tasks: installservice
