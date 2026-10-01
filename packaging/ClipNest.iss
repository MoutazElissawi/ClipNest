; Build through Build_Installer.bat so PayloadDir contains the private runtime.
#ifndef PayloadDir
  #error Supply /DPayloadDir with the staged runtime directory
#endif
#ifndef AppVersion
  #define AppVersion "1.5.1"
#endif
[Setup]
AppId={{B802DB77-26F6-4806-BBF3-2AC0BE0B48E4}
AppName=ClipNest
AppVersion={#AppVersion}
AppPublisher=ClipNest
DefaultDirName={localappdata}\Programs\ClipNest
DefaultGroupName=ClipNest
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
MinVersion=10.0
WizardStyle=modern
DisableProgramGroupPage=yes
LicenseFile={#PayloadDir}\LICENSE.txt
OutputDir=..\dist
OutputBaseFilename=ClipNest-Setup-{#AppVersion}-x64
Compression=lzma2
SolidCompression=yes
AppMutex=Local\ClipNest.Running
CloseApplications=no
RestartApplications=no
UninstallDisplayName=ClipNest
SetupIconFile={#PayloadDir}\clipnest\assets\clipnest.ico
UninstallDisplayIcon={app}\clipnest\assets\clipnest.ico
; Never delete ClipNest's separate AppData, clips or exports.

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\ClipNest"; Filename: "{app}\runtime\pythonw.exe"; Parameters: "-s -E ""{app}\Launch_ClipNest.pyw"""; WorkingDir: "{app}"; IconFilename: "{app}\clipnest\assets\clipnest.ico"; AppUserModelID: "ClipNest.Desktop"
Name: "{autodesktop}\ClipNest"; Filename: "{app}\runtime\pythonw.exe"; Parameters: "-s -E ""{app}\Launch_ClipNest.pyw"""; WorkingDir: "{app}"; Tasks: desktopicon; IconFilename: "{app}\clipnest\assets\clipnest.ico"; AppUserModelID: "ClipNest.Desktop"

[Run]
Filename: "{app}\runtime\pythonw.exe"; Parameters: "-s -E ""{app}\Launch_ClipNest.pyw"""; WorkingDir: "{app}"; Description: "Launch ClipNest"; Flags: nowait postinstall skipifsilent
