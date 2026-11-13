# Genera el instalador:  v2\installer\Output\AgenteCorreosBN_<versión>_Setup.exe
#
#   powershell -ExecutionPolicy Bypass -File installer\construir.ps1
#
# Compila desde un entorno virtual limpio (.venv_build) para que el paquete lleve solo lo que usa el
# programa. Si en la carpeta  ..\data  existe agencias.json, el instalador lo incluye como lista de partida.

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

$venv = Join-Path $raiz ".venv_build"
if (-not (Test-Path "$venv\Scripts\python.exe")) {
    Write-Host "Creando entorno de compilación…"
    python -m venv $venv
}
$py = "$venv\Scripts\python.exe"
& $py -m pip install --quiet --upgrade pip
& $py -m pip install --quiet -r requirements-ui.txt pyinstaller

$version = (& $py -c "from agente_correos import __version__; print(__version__)").Trim()
Write-Host "Versión $version"

Remove-Item -Recurse -Force "$raiz\build", "$raiz\dist" -ErrorAction SilentlyContinue
& $py -m PyInstaller --noconfirm --clean --distpath "$raiz\dist" --workpath "$raiz\build" "$raiz\installer\AgenteCorreosBN.spec"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falló" }

$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
          "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "No se encontró Inno Setup 6 (ISCC.exe)" }
& $iscc "/DMyAppVersion=$version" "$raiz\installer\AgenteCorreosBN.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup falló" }

Get-ChildItem "$raiz\installer\Output\*.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1 |
    ForEach-Object { Write-Host ("Listo: {0} ({1:N0} MB)" -f $_.FullName, ($_.Length / 1MB)) }
