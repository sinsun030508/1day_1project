// 랭킹 저장소. Supabase가 설정돼 있으면 온라인, 아니면 이 브라우저에만 저장.
import { CONFIG } from "./config.js";

const LOCAL_KEY = "staring-contest:local-scores";
export const isOnline = Boolean(CONFIG.supabaseUrl && CONFIG.supabaseKey);

const headers = () => ({
  apikey: CONFIG.supabaseKey,
  "Content-Type": "application/json",
});

function readLocal() {
  try {
    return JSON.parse(localStorage.getItem(LOCAL_KEY)) ?? [];
  } catch {
    return [];
  }
}

export async function submitScore(nickname, timeMs) {
  const row = { nickname, time_ms: Math.round(timeMs) };
  if (!isOnline) {
    try {
      const scores = readLocal();
      scores.push({ ...row, created_at: new Date().toISOString() });
      localStorage.setItem(LOCAL_KEY, JSON.stringify(scores));
    } catch {}
    return;
  }
  const res = await fetch(`${CONFIG.supabaseUrl}/rest/v1/scores`, {
    method: "POST",
    headers: { ...headers(), Prefer: "return=minimal" },
    body: JSON.stringify(row),
  });
  if (!res.ok) throw new Error(`기록 저장 실패 (${res.status})`);
}

/** 닉네임별 최고 기록 상위 N개 */
export async function fetchLeaderboard(limit = 20) {
  if (!isOnline) {
    const best = new Map();
    for (const s of readLocal()) {
      if (!best.has(s.nickname) || best.get(s.nickname).time_ms < s.time_ms) best.set(s.nickname, s);
    }
    return [...best.values()].sort((a, b) => b.time_ms - a.time_ms).slice(0, limit);
  }
  const url = `${CONFIG.supabaseUrl}/rest/v1/leaderboard?select=nickname,time_ms,created_at&order=time_ms.desc&limit=${limit}`;
  const res = await fetch(url, { headers: headers() });
  if (!res.ok) throw new Error(`랭킹 불러오기 실패 (${res.status})`);
  return res.json();
}
