# Darcy-Weisbach 관수로 분석기

레이놀즈 수와 상대조도를 이용해 유동 상태를 판별하고, Darcy 마찰계수와 손실수두를 계산합니다.

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
python darcy_weisbach.py --velocity 2 --diameter 0.1 --length 20 --roughness 0.000045
```

기본적으로 `output/darcy_weisbach_report.txt`와
`output/darcy_weisbach_analysis.png`가 생성됩니다. 출력 폴더는
`--output-dir results`처럼 변경할 수 있습니다.

입력값의 단위는 유속 m/s, 관경·관 길이·절대조도 m, 밀도 kg/m³,
동점성계수가 아닌 **동적 점성계수** Pa·s입니다. 기본 유체값은 20°C 물의 근사값입니다.

## 계산 기준

- `Re < 2300`: 층류, `f = 64 / Re`
- `2300 <= Re < 4000`: 천이 영역으로 표시하며 참고용으로 `64 / Re`를 사용
- `Re >= 4000`: Colebrook-White 식을 구간 이분법으로 수치해석
- 손실수두: `h_f = f (L/D) V²/(2g)`

## 파일 구성

- `darcy_weisbach.py`: 계산 함수와 명령줄 실행 프로그램
- `test_darcy_weisbach.py`: 단위 테스트
- `requirements.txt`: 그래프 저장에 필요한 의존성
- `output/`: 실행 후 생성되는 TXT 보고서와 PNG 그래프

테스트는 다음처럼 실행합니다.

```powershell
python -m unittest -v
```
