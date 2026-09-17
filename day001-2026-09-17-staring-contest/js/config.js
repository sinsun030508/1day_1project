// 게임 설정. Supabase 값이 비어 있으면 랭킹은 이 브라우저(localStorage)에만 저장된다.
export const CONFIG = {
  // 상대(제작자)의 기록: 1분 20초. 이보다 오래 버티면 사용자 승리.
  opponentRecordMs: 80_000,

  // Supabase 프로젝트 설정 (Project Settings → API)
  supabaseUrl: "",
  supabaseKey: "", // anon(public) 또는 publishable 키. service_role 키는 절대 넣지 말 것.

  // 눈 감김 판정
  closedHoldMs: 80,       // 이 시간 이상 연속으로 감겨 있어야 '감음'으로 판정 (노이즈 방지)
  faceLostLimitMs: 1500,  // 얼굴이 이 시간 이상 안 보이면 패배 (카메라 가리기 방지)
  calibrationMs: 2500,    // 시작 전 뜬 눈 기준값 측정 시간
};
