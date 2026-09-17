# Day 001 · 눈싸움 챌린지

제작자의 기록 **1분 20초**보다 오래 눈을 뜨고 버티면 승리하는 웹 게임입니다.

- 상대: 제작자 사진 (`assets/opponent.jpg`)
- 눈 감김 감지: 웹캠 + [MediaPipe Face Landmarker](https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker)의 `eyeBlinkLeft/Right` 블렌드셰이프
  - 영상은 브라우저 안에서만 처리되고 서버로 전송되지 않음
- 랭킹: 로그인 없이 닉네임으로 등록, 닉네임별 최고 기록 표시 (Supabase)
- 배포: GitHub Pages (정적 파일, 빌드 과정 없음)

## 규칙

1. 닉네임 입력 → 카메라 허용
2. 2.5초 동안 뜬 눈 상태를 측정해서 사람마다 감김 기준값을 보정
3. 3초 카운트다운 후 시작
4. 다음 중 하나가 되면 종료되고 기록이 저장됨
   - 눈이 0.08초 이상 감김 (깜빡임 포함)
   - 얼굴이 1.5초 이상 화면에서 사라짐
   - 탭 전환 등으로 게임 화면을 벗어남
5. 1:20.00을 넘기면 승리. 그 뒤로도 계속 버티면 랭킹이 올라감

## 파일 구성

```
index.html          화면 (시작 / 게임 / 결과)
style.css
js/config.js        상대 기록, Supabase 접속 정보, 판정 기준값
js/eye-detector.js  MediaPipe로 눈 감김 점수 읽기
js/ranking.js       Supabase REST API (미설정 시 localStorage)
js/app.js           게임 흐름
supabase/schema.sql 랭킹 테이블 + RLS + leaderboard 뷰
assets/opponent.jpg 상대 사진 (3:4 세로 비율 권장)
```

## 설정

### 1. Supabase (랭킹)

1. [supabase.com](https://supabase.com)에서 새 프로젝트 생성
2. SQL Editor에서 `supabase/schema.sql` 실행
3. Project Settings → API에서 **Project URL**과 **anon / publishable 키**를 `js/config.js`에 입력
   - anon 키는 공개돼도 되는 키입니다 (RLS로 조회·등록만 허용). `service_role` 키는 절대 넣지 마세요.

설정하지 않으면 랭킹은 각자의 브라우저에만 저장됩니다.

### 2. GitHub Pages (배포)

레포 Settings → Pages → Source: `Deploy from a branch`, Branch: `main` / `/ (root)`

배포 주소: https://sinsun030508.github.io/1day_1project/day001-2026-09-17-staring-contest/

## 로컬 실행

카메라는 `https` 또는 `localhost`에서만 동작합니다.

```bash
python -m http.server 5501
```

## 한계

- 점수는 클라이언트에서 전송하므로 마음먹고 조작하면 가짜 기록을 넣을 수 있습니다 (DB 제약으로 1초~1시간만 허용).
- 조명이 어둡거나 안경 반사가 심하면 감지가 부정확할 수 있습니다.
