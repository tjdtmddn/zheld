# Darcy-Weisbach 관수로 분석기

레이놀즈 수와 상대조도를 이용해 유동 상태를 판별하고, Darcy 마찰계수,
주손실·부차적 손실·전체 손실수두·압력손실을 계산합니다.

## GitHub 저장소

이 프로젝트의 GitHub 저장소는 [tjdtmddn/zheld](https://github.com/tjdtmddn/zheld)입니다.
저장소에서 내려받아 실행하려면 다음 명령을 사용합니다.

```powershell
git clone https://github.com/tjdtmddn/zheld.git
cd zheld
```

## 실행

```powershell
pip install -r requirements.txt
python darcy_weisbach.py --flow-rate 0.015 --diameter 0.1 --length 20 --material commercial-steel --minor-k 3.5
```

기본적으로 `output/darcy_weisbach_report.txt`와
`output/darcy_weisbach_analysis.png`가 생성됩니다. 출력 폴더는
`--output-dir results`처럼 변경할 수 있습니다.

`--velocity`(m/s)와 `--flow-rate`(m³/s) 중 하나를 입력합니다. 관 재질을
선택하거나 `--roughness`로 절대조도(m)를 직접 지정할 수 있습니다.
관경·관 길이·절대조도의 단위는 m, 밀도는 kg/m³, 점성계수는
동점성계수가 아닌 **동적 점성계수** Pa·s입니다. 기본 유체값은 20°C 물의
근사값이며, `--temperature`를 지정하면 0~100°C 물의 물성을 사용합니다.
`--minor-k`는 밸브·엘보·입출구 등의 부차적 손실계수 합이며 기본값은 0입니다.
`--pump-efficiency`를 0~1로 지정하면 필요한 펌프동력도 계산합니다.
`--fluid water` 또는 `--fluid air`로 유체 프리셋을 선택할 수 있습니다.
사용자 지정 유체는 GUI 또는 CSV에서 밀도와 동적 점성계수를 직접 입력할 수
있습니다.

### VS Code에서 import 경고가 표시될 때

이 프로젝트는 `darcy_weisbach_gui.py`, `phase_two.py`,
`advanced_analysis.py`가 같은 폴더에 있는 구조입니다. VS Code에서 개별
파일만 열면 Pylance가 같은 폴더를 프로젝트 루트로 인식하지 못해
`Import "phase_two" could not be resolved`와 같은 경고를 표시할 수 있습니다.

다음 폴더를 워크스페이스로 열어야 합니다.

```text
C:\Users\seung\Desktop\코딩\zheld
```

VS Code에서 `파일 > 폴더 열기`를 선택하거나 터미널에서 다음 명령을
실행합니다.

```powershell
code "C:\Users\seung\Desktop\코딩\zheld"
```

프로젝트에는 `pyrightconfig.json`과 `.vscode/settings.json`도 포함되어
있어 폴더를 올바른 워크스페이스로 열면 Pylance가 프로젝트 파일과 로컬
import를 자동으로 찾습니다. 설정을 적용한 뒤 `Python: Restart Language
Server` 명령을 실행하면 기존 진단이 갱신됩니다.

프로젝트 폴더를 한 번에 올바르게 열려면 `zheld.code-workspace` 파일을
VS Code에서 열어도 됩니다. 이 파일은 `zheld` 폴더를 단일 워크스페이스로
등록하고 Pylance의 workspace 분석을 활성화합니다.

## GUI 실행

Tkinter 기반 GUI는 다음 실행 파일로 시작할 수 있습니다.

```powershell
.\run_gui.bat
```

PowerShell에서는 다음 명령도 사용할 수 있습니다.

```powershell
.\run_gui.ps1
```

실행 스크립트는 프로젝트의 `.venv`를 먼저 사용하고, 없으면 설치된
Python 3.13을 사용합니다. `tkinter`와 `matplotlib`를 먼저 확인하므로
잘못된 Python 환경으로 실행되는 문제를 줄일 수 있습니다. 의존성이 없는
환경에서는 다음 명령으로 설치합니다.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`run_gui.bat`를 더블클릭해도 GUI를 실행할 수 있습니다.

EXE를 만들려면 PowerShell에서 다음을 실행합니다.

```powershell
.\build_exe.ps1
```

완료 후 `dist\DarcyWeisbachAnalyzer.exe`가 생성됩니다. 처음 실행할 때는
PyInstaller 설치로 인터넷 연결이 필요할 수 있습니다.

GUI에서는 유량/유속, 관 재질/조도, 물 온도, 부차적 손실계수와 펌프
효율을 입력하고 계산 결과를 확인할 수 있습니다. 계산 후 보고서와 그래프를
버튼으로 저장할 수 있습니다. `입력 CSV 저장`은 현재 입력창의 값을 저장하고,
`결과 CSV 저장`은 현재 기간 필터가 적용된 처리 결과와 기준 판정을 저장합니다.
`PDF 보고서`는 계산식과 경고를 포함한 PDF를 저장하며, 여러 행을 계산한 뒤
`결과 비교`를 누르면 유속·Reynolds 수·손실수두·압력손실·펌프동력을
비교할 수 있습니다. 사용자 지정 유체를 선택하면 밀도와 동적 점성계수를
직접 입력할 수 있습니다.
숫자 형식, 필수값, 음수, 펌프 효율 범위가 잘못되면 오류 안내가 표시되고
문제가 있는 입력창으로 커서가 돌아가므로 값을 수정한 뒤 다시 사용할 수 있습니다.
입력과 결과 영역이 긴 경우 창 오른쪽 스크롤바 또는 마우스 휠로 전체 화면을
확인할 수 있습니다. `정수두/높이차`를 입력하면 필요 펌프수두와 펌프동력에
반영됩니다.

## 1단계 학습 기능

- 부차적 손실을 `이름:개수:K` 형식으로 입력할 수 있습니다.
  예: `입구:1:0.5,엘보:4:0.3`
- 유량은 `m³/s`, `L/s`, `m³/h`, 관경·길이는 `m`, `mm`, `km` 단위로
  입력할 수 있으며 계산 시 SI 단위로 변환됩니다.
- 결과 표의 행을 선택하면 선택한 결과의 상세값과 계산식이 표시됩니다.
- 그래프 항목에서 전체손실수두, 압력손실, 유속, Reynolds 수, 필요
  펌프수두, 펌프동력을 선택할 수 있습니다.
- `프로젝트 저장`과 `프로젝트 열기`로 입력값·기준값·기간·그래프 설정을
  JSON 파일로 저장하고 복원할 수 있습니다.
- 결과 CSV에는 주요 입력 조건, 결과, 계산식과 기준 판정이 포함됩니다.
- 상대조도가 지나치게 큰 경우와 천이영역을 경고합니다.
- 천이영역 처리에서 `warn`은 경고와 함께 참고값을 계산하고, `stop`은
  계산을 중단하여 입력 또는 운전조건을 다시 확인하게 합니다.

## 2단계 학습 기능

- `펌프 곡선 분석`에서 `Q:H` 점을 입력하고 시스템 곡선
  `H_system = H_static + RQ²`와의 운전점을 찾을 수 있습니다. 펌프 곡선,
  시스템 곡선, 운전점을 그림으로 함께 표시합니다.
- `직렬/병렬 관로`에서 관로별 저항값을 입력할 수 있습니다.
  직렬은 `R_eq = ΣR_i`, 병렬은
  `1/sqrt(R_eq) = Σ1/sqrt(R_i)`로 등가저항을 계산합니다.
- 병렬 관로에서는 전체 유량을 입력하면 각 분기 유량과 합계도 표시합니다.
- 두 기능은 기본 관로 계산과 분리된 학습용 도구이며, 모든 입력은 양수 또는
  0 이상인지 검사합니다.

## 3~12단계 학습 기능

프로그램은 다음 순서로 기능을 확장했습니다.

1. 기본 Darcy-Weisbach 계산과 입력 검증
2. 단위 변환, 부차손실 부품, 계산식·중간값 표시
3. 펌프 곡선과 시스템 곡선의 운전점
4. 직렬·병렬 관로의 등가저항과 분기 유량
5. 직사각형 관로의 수력직경 계산
6. 입력 변수 민감도 분석
7. 입력 범위 기반 몬테카를로 불확실성 분석
8. 펌프 직렬·병렬 조합 곡선
9. 결과 요약과 CSV/프로젝트 저장
10. 결과 그래프 및 기준값 갱신
11. 다중노드 관망의 노드 수두·관로 유량 해석
12. 통합 GUI, 오류 안내, 문서, 회귀 테스트
13. 유체 프리셋·사용자 지정 물성, CSV 단위 변환·오류 파일
14. 결과 비교, PDF 보고서, PyInstaller EXE 빌드

`민감도·불확실성` 창에서는 현재 기본 입력을 기준으로 유량·관경·관 길이·
정수두를 바꿔 손실수두 변화를 확인할 수 있습니다. 범위 입력은
`변수=최소:최대` 형식입니다.

`다중노드 관망` 창에서는 고정 수두 노드와 미지 수두 노드를 함께 입력하고,
각 관로를 `이름:시작:끝:저항` 형식으로 입력합니다. 관로 손실 모델은
`H_loss = R Q²`이며 Newton 반복으로 노드 수두와 관로 유량을 계산합니다.

### CSV 입력

GUI의 `CSV 불러오기`는 첫 번째 데이터 행을 입력창에 불러옵니다.
`CSV 일괄 계산`은 모든 행을 계산해 결과 CSV로 저장합니다. 입력 CSV는
UTF-8 형식이며 다음 SI 단위 열 이름을 사용합니다.
`입력 CSV 양식 저장` 버튼을 누르면 이 형식의 예시 2개가 포함된 템플릿을
만들 수 있으며, 예시 행을 수정하거나 행을 추가해 바로 불러올 수 있습니다.
CSV 파일 선택창은 프로그램 폴더의 `csv` 폴더에서 시작하며, 이 폴더에
기본 관로, 재질 비교, 유속 입력, 펌프 운전 예시 CSV도 함께 제공됩니다.

```text
flow_rate_m3_s,velocity_m_s,diameter_m,pipe_length_m,material,absolute_roughness_m,temperature_c,minor_loss_coefficient,minor_loss_components,static_head_m,pump_efficiency,transitional_policy
```

각 행에서 `flow_rate_m3_s`와 `velocity_m_s` 중 하나, `material`과
`absolute_roughness_m` 중 하나를 입력합니다. `temperature_c`,
`minor_loss_coefficient`, `pump_efficiency`는 선택 열이며, 생략 시 각각
기본 물성, 0, 펌프동력 미계산으로 처리됩니다.
`static_head_m`은 펌프가 극복해야 하는 정수두 또는 높이차(m)이며 기본값은
0입니다. 필요 펌프수두는 전체 손실수두와 정수두의 합으로 계산합니다.
`minor_loss_components` 열에는 `이름:개수:K` 항목을 쉼표로 구분해 입력할
수 있습니다.

`fluid` 열에는 `water`, `air`, `custom`을 사용할 수 있습니다.
`custom`인 경우 `density_kg_m3`와 `dynamic_viscosity_pa_s`도 입력해야 합니다.
PDF 보고서는 GUI의 `PDF 보고서` 버튼으로 저장할 수 있습니다.
여러 행을 계산한 뒤 `결과 비교` 버튼으로 유속, Reynolds 수, 손실수두,
압력손실, 펌프동력을 한 표에서 비교할 수 있습니다.

사용자 단위를 직접 입력하려면 다음 대체 열을 사용할 수 있습니다.

```text
flow_rate,flow_unit,velocity,velocity_unit,diameter,diameter_unit,pipe_length,length_unit,absolute_roughness,roughness_unit
```

예를 들어 `flow_rate=15, flow_unit=L/s, diameter=100,
diameter_unit=mm`은 각각 `0.015 m³/s`, `0.1 m`로 변환됩니다.
유속은 `velocity_unit=m/s`만 지원하며, 유량 단위는 `m³/s`, `L/s`,
`m³/h`, 길이·조도 단위는 `m`, `mm`, `km`를 지원합니다. 기존 SI 열과
대체 열을 동시에 입력하면 SI 열을 우선하지 않고 값이 충돌할 수 있으므로
한 행에서는 한 형식만 사용하세요.

CSV를 일괄 계산할 때 잘못된 행은 행 번호와 오류 원인을 모아 표시하고,
계산 가능한 정상 행은 결과에 포함합니다. 모든 행이 잘못되면 결과 파일을
저장하지 않습니다. 필수 입력 열, 날짜, 단위, 숫자, 유량/유속 조합,
재질/조도 조합도 계산 전에 검사합니다. 오류가 있는 경우 결과 파일과
같은 폴더에 `<결과파일명>_errors.csv`가 생성됩니다.

여러 행의 기간별 표·그래프를 사용하려면 선택적으로 `timestamp` 열을
추가합니다. 값은 `YYYY-MM-DD` 또는 `YYYY-MM-DD HH:MM:SS` 형식으로 입력할
수 있습니다. GUI의 시작/종료 기간을 바꾼 뒤 `결과 갱신`을 누르면 해당 기간만
표와 그래프에 표시됩니다. 최대 유속, 최대 전체손실수두, 최대 압력손실 기준을
입력하면 각 행이 `정상` 또는 `초과`로 판정됩니다.

## 계산 기준

- `Re < 2300`: 층류, `f = 64 / Re`
- `2300 <= Re < 4000`: 천이 영역으로 표시하며 참고용으로 `64 / Re`를 사용
- `Re >= 4000`: Colebrook-White 식을 구간 이분법으로 수치해석
- 주손실수두: `h_f = f (L/D) V²/(2g)`
- 부차적 손실수두: `h_m = K V²/(2g)`
- 전체 손실수두: `h_total = h_f + h_m`
- 압력손실: `Δp = ρ g h_total`
- `2300 <= Re < 4000`에서는 참고값을 표시하고 천이영역 경고를 출력합니다.

## 파일 구성

- `darcy_weisbach.py`: 계산 함수와 명령줄 실행 프로그램
- `phase_two.py`: 펌프 곡선, 직렬·병렬 관로 계산 함수
- `advanced_analysis.py`: 민감도·몬테카를로·펌프 조합·관망 분석
- `darcy_weisbach_gui.py`: 직접 입력, CSV, 그래프, PDF, 결과 비교 GUI
- `test_darcy_weisbach.py`: 단위 테스트
- `requirements.txt`: Matplotlib와 EXE 빌드 의존성
- `build_exe.ps1`, `zheld.spec`: PyInstaller EXE 빌드 설정
- `csv/`: 관로·재질·유속·펌프 운전 예시 CSV
- `output/`: 실행 후 생성되는 TXT 보고서와 PNG 그래프
- `dist/`: EXE 빌드 후 생성되는 배포 폴더

테스트는 다음처럼 실행합니다.

```powershell
python -m unittest -v
```

전체 Python 파일을 문법 검사하려면 다음을 실행합니다.

```powershell
python -m compileall -q .
```

## EXE 빌드 및 배포

PowerShell에서 다음 명령을 실행하면 PyInstaller가 필요한 패키지를 설치하고
GUI 실행 파일을 생성합니다.

```powershell
.\build_exe.ps1
```

생성 파일:

```text
dist\DarcyWeisbachAnalyzer.exe
```

EXE는 단일 파일로 실행할 수 있으며, CSV 예시 파일은 소스 배포 시
`csv` 폴더를 함께 제공하는 것을 권장합니다. 빌드 중 생성되는 `build`
폴더는 임시 파일이고, `dist`는 배포 산출물입니다.
