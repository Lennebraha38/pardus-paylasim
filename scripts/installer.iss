[Setup]
AppName=Pardus Paylaşım Agent
AppVersion=1.0.0
DefaultDirName={autopf}\Pardus Paylasim Agent
DefaultGroupName=Pardus Paylasim Agent
UninstallDisplayIcon={app}\pardus-paylasim-agent.exe
Compression=lzma2
SolidCompression=yes
OutputDir=..\dist
OutputBaseFilename=PardusPaylasimAgent_Setup
ArchitecturesInstallIn64BitMode=x64

[Files]
Source: "..\dist\pardus-paylasim-agent\pardus-paylasim-agent.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\pardus-paylasim-agent\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Pardus Paylaşım Agent"; Filename: "{app}\pardus-paylasim-agent.exe"
Name: "{autodesktop}\Pardus Paylaşım Agent"; Filename: "{app}\pardus-paylasim-agent.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Masaüstü kısayolu oluştur"; GroupDescription: "Ek kısayollar:"

[Run]
Filename: "{app}\pardus-paylasim-agent.exe"; Description: "Uygulamayı çalıştır"; Flags: nowait postinstall skipifsilent
