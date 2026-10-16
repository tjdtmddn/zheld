$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$systemPython = "C:\Users\seung\AppData\Local\Programs\Python\Python313\python.exe"

if (Test-Path -LiteralPath $venvPython) {
    $python = $venvPython
} elseif (Test-Path -LiteralPath $systemPython) {
    $python = $systemPython
} else {
    throw "Python을 찾을 수 없습니다. Python 3.11 이상을 설치하세요."
}

& $python -c "import tkinter, matplotlib"
if ($LASTEXITCODE -ne 0) {
    Write-Error "필수 모듈이 없습니다. 다음 명령으로 설치하세요: `"$python`" -m pip install -r requirements.txt"
    exit 1
}

& $python (Join-Path $PSScriptRoot "darcy_weisbach_gui.py")
exit $LASTEXITCODE
