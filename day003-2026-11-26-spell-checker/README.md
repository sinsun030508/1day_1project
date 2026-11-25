# Day 003 · 맞춤법 자동 교정기

글을 쓰는 동안 맞춤법·띄어쓰기를 검사해서, 틀리면 입력 커서 위에 올바른 문장을 말풍선으로 보여주는 윈도우 상주 프로그램입니다.
Python + tkinter + [Kiwi](https://github.com/bab2min/kiwipiepy) + [pynput](https://pynput.readthedocs.io/)으로 만들었습니다.

## 실행

`run.bat`을 더블클릭하면 됩니다. 처음 실행할 때 가상환경을 만들고 필요한 라이브러리를 설치합니다.

직접 실행하려면:

```bash
python -m venv .venv && .venv/Scripts/python.exe -m pip install -r requirements.txt
```
```bash
.venv/Scripts/python.exe live_fix.py   # 실시간 말풍선
.venv/Scripts/python.exe autofix.py    # 선택 영역 교정 단축키
```

부팅할 때 자동으로 켜지게 하려면 `Win+R` → `shell:startup` 폴더에 `run.bat` 바로가기를 넣으세요.

## 기능

| 파일 | 동작 |
|------|------|
| `live_fix.py` | 스페이스·엔터·`. , ? !`를 누르면 방금 쓴 문장을 검사해, 틀린 곳이 있으면 커서 위에 교정 문장을 띄움 (5초 뒤 또는 클릭하면 닫힘) |
| `autofix.py` | 텍스트를 선택하고 `Ctrl+Alt+K`를 누르면 교정된 문장으로 바로 바꿈 |
| `spell_fix.py` | 교정 엔진. 단독으로 `python spell_fix.py "문장"` 실행 가능 |

예시:

```
몇일전에 금새끝낼께요        → 며칠 전에 금세 끝낼게요
학교갔다가 할수있는거 다했어 → 학교 갔다가 할 수 있는 거 다 했어
```

## 동작 원리

1. **키 감지** — pynput으로 문장이 끝나는 키 입력을 감지
2. **입력창 글 읽기** — 한글은 IME가 자모를 조합하므로 키 입력으로는 글자를 알 수 없음 → UI Automation으로 입력창의 글을 직접 읽음
3. **교정**
   - 단어 사전: `몇일→며칠`, `설겆이→설거지` 등
   - 정규식 규칙: `되요→돼요`, `하지안아→하지 않아` (`되도록`처럼 맞는 표현은 제외)
   - ㄹ받침 판별: `(ord(ch) - 0xAC00) % 28 == 8` → `할께→할게`, `선생님께`는 유지
   - 띄어쓰기: Kiwi 형태소 분석기의 `space()`
4. **말풍선** — tkinter 창을 `WS_EX_NOACTIVATE`로 띄워서 입력 중인 창의 포커스를 뺏지 않음

## 참고

- `League of Legends` 창이 앞에 있으면 검사를 멈춥니다.
- 카카오톡처럼 자체 입력창을 쓰는 앱은 글을 읽지 못할 수 있습니다.
- 커서 위치를 알려주지 않는 앱(크롬 등)에서는 말풍선이 마우스 위치 위에 뜹니다.
- 규칙 기반이라 문맥이 필요한 `되/돼` 구분 등은 일부만 잡습니다.
