; ============================================================================
; Instalador de Agente de Correos BN v2 â€” Inno Setup
; ============================================================================
; Se genera con installer\construir.ps1 (compila con PyInstaller y luego con ISCC).
; Instala SIN permisos de administrador, en el perfil del propio usuario
; ({localappdata}), como AutoPSJN: en una PC del banco el operador puede no ser admin.
;
; Los datos de cada persona (perfil, firma, registro de actividad) viven en
; %APPDATA%\AgenteCorreosBN y NO se tocan al actualizar ni al desinstalar.
; ============================================================================

#ifndef MyAppVersion
  #define MyAppVersion "2.1.1-beta"
#endif
#define MyAppName "Agente de Correos BN"
#define MyAppExeName "AgenteCorreosBN.exe"
#define MyDistDir "..\dist\AgenteCorreosBN"

[Setup]
AppId={{7D3F2B1E-5A94-4C0E-9B67-AC0F2E7C0B12}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=SecciÃ³n Caja y Valores en Custodia - Banco de la NaciÃ³n
DefaultDirName={localappdata}\AgenteCorreosBN
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=AgenteCorreosBN_{#MyAppVersion}_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\assets\icono_programa.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el Escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "{#MyDistDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
; Lista de agencias de partida (si existe junto al cÃ³digo al compilar). Solo se copia la primera vez:
; despuÃ©s la edita cada persona desde ConfiguraciÃ³n y vive en la carpeta compartida.
Source: "..\data\agencias.json"; DestDir: "{app}\data"; Flags: onlyifdoesntexist skipifsourcedoesntexist
; Valores propios de la institución (jefatura, copia fija, carpeta de red). No está en el repositorio: se coloca en
; data\institucional.json antes de compilar. Ver agente_correos\institucional.py.
Source: "..\data\institucional.json"; DestDir: "{app}\data"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir {#MyAppName} ahora"; Flags: nowait postinstall skipifsilent
