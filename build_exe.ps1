$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $python = "python"
}

& $python -m pip install -r requirements.txt pyinstaller
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller 설치에 실패했습니다."
}
& $python -m PyInstaller --clean --noconfirm zheld.spec
if ($LASTEXITCODE -ne 0) {
    throw "EXE 빌드에 실패했습니다."
}
Write-Output "dist\DarcyWeisbachAnalyzer.exe 생성 완료"
