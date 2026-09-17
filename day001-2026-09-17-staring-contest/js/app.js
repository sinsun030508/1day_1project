import { CONFIG } from "./config.js";
import { EyeDetector } from "./eye-detector.js";
import { fetchLeaderboard, isOnline, submitScore } from "./ranking.js";

const $ = (id) => document.getElementById(id);
const NICK_KEY = "staring-contest:nickname";

const els = {
  startForm: $("start-form"),
  nickname: $("nickname"),
  startError: $("start-error"),
  boardStart: $("board-start"),
  boardResult: $("board-result"),
  boardMode: $("board-mode"),
  opponent: document.querySelector(".fighter.opponent"),
  opponentImg: $("opponent-img"),
  player: document.querySelector(".fighter.player"),
  playerName: $("player-name"),
  video: $("video"),
  eyeState: $("eye-state"),
  status: $("status"),
  timer: $("timer"),
  progressFill: $("progress-fill"),
  meterFill: $("meter-fill"),
  meterThreshold: $("meter-threshold"),
  resultEyebrow: $("result-eyebrow"),
  resultTitle: $("result-title"),
  resultTime: $("result-time"),
  resultDesc: $("result-desc"),
  resultError: $("result-error"),
};

const detector = new EyeDetector();
let detectorReady = null; // Promise, 한 번만 로드

const game = {
  phase: "idle", // idle | calibrating | countdown | playing | over
  nickname: "",
  stream: null,
  rafId: 0,
  threshold: 0.5,
  samples: [],
  phaseStart: 0,
  startTime: 0,
  closedSince: null,
  faceLostSince: null,
  beat: false,
  lastResult: null,
};

// ---------------- 공통 ----------------
function show(screen) {
  document.querySelectorAll(".screen").forEach((s) => s.classList.toggle("is-active", s.id === `screen-${screen}`));
  window.scrollTo({ top: 0 });
}

function formatTime(ms) {
  const total = Math.max(0, Math.floor(ms / 10));
  const cs = total % 100;
  const s = Math.floor(total / 100) % 60;
  const m = Math.floor(total / 6000);
  return `${m}:${String(s).padStart(2, "0")}.${String(cs).padStart(2, "0")}`;
}

function formatGap(ms) {
  return `${(Math.abs(ms) / 1000).toFixed(2)}초`;
}

function escapeHtml(str) {
  return str.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function loadNickname() {
  try {
    return localStorage.getItem(NICK_KEY) ?? "";
  } catch {
    return "";
  }
}

function saveNickname(name) {
  try {
    localStorage.setItem(NICK_KEY, name);
  } catch {}
}

// ---------------- 랭킹 ----------------
async function renderBoard(listEl, highlight) {
  listEl.innerHTML = `<li class="empty">불러오는 중…</li>`;
  let rows;
  try {
    rows = await fetchLeaderboard(20);
  } catch (err) {
    listEl.innerHTML = `<li class="empty">${escapeHtml(err.message)}</li>`;
    return;
  }

  // 제작자 기록을 기준선으로 끼워 넣는다
  const owner = { nickname: "상대", time_ms: CONFIG.opponentRecordMs, owner: true };
  const all = [...rows, owner].sort((a, b) => b.time_ms - a.time_ms);

  listEl.innerHTML = all
    .map((r) => {
      const isMe = highlight && !r.owner && r.nickname === highlight.nickname && r.time_ms === highlight.time_ms;
      const cls = [r.owner && "is-owner", isMe && "is-me"].filter(Boolean).join(" ");
      const beat = !r.owner && r.time_ms > CONFIG.opponentRecordMs ? " beat" : "";
      return `<li class="${cls}"><span class="name">${escapeHtml(r.nickname)}</span><span class="time${beat}">${formatTime(r.time_ms)}</span></li>`;
    })
    .join("");
}

// ---------------- 게임 흐름 ----------------
async function startGame(nickname) {
  game.nickname = nickname;
  els.playerName.textContent = nickname;
  els.startError.textContent = "";
  resetHud();
  show("game");
  setStatus("카메라 권한을 요청하고 있어요…");

  try {
    game.stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } },
      audio: false,
    });
  } catch (err) {
    return abort(
      err.name === "NotAllowedError"
        ? "카메라 권한이 거부됐어요. 브라우저 주소창에서 카메라를 허용해 주세요."
        : "카메라를 사용할 수 없어요. 다른 앱이 사용 중인지 확인해 주세요."
    );
  }

  els.video.srcObject = game.stream;
  await els.video.play();

  setStatus("눈 감지 모델을 불러오고 있어요… (처음 한 번만 몇 초 걸려요)");
  try {
    detectorReady ??= detector.init(els.video);
    await detectorReady;
  } catch (err) {
    detectorReady = null;
    console.error(err);
    return abort("눈 감지 모델을 불러오지 못했어요. 새로고침 후 다시 시도해 주세요.");
  }
  if (game.phase === "over") return; // 로딩 중에 그만두기

  enterPhase("calibrating");
  game.samples = [];
  loop();
}

function enterPhase(phase) {
  game.phase = phase;
  game.phaseStart = performance.now();
}

function loop() {
  game.rafId = requestAnimationFrame(loop);
  const now = performance.now();
  const { face, blink } = detector.read();
  updateMeter(face, blink);

  if (game.phase === "calibrating") return tickCalibration(now, face, blink);
  if (game.phase === "countdown") return tickCountdown(now, face, blink);
  if (game.phase === "playing") return tickPlaying(now, face, blink);
}

function tickCalibration(now, face, blink) {
  if (!face) {
    game.samples = [];
    game.phaseStart = now;
    return setStatus("얼굴이 화면 가운데에 오도록 맞춰주세요");
  }
  game.samples.push(blink);
  const left = Math.ceil((CONFIG.calibrationMs - (now - game.phaseStart)) / 1000);
  setStatus(`눈을 편하게 뜨고 정면을 봐주세요… 측정 중 ${Math.max(left, 1)}`);

  if (now - game.phaseStart >= CONFIG.calibrationMs) {
    const sorted = [...game.samples].sort((a, b) => a - b);
    const baseline = sorted[Math.floor(sorted.length / 2)] ?? 0;
    game.threshold = Math.min(0.7, Math.max(0.35, baseline + 0.25));
    els.meterThreshold.style.left = `${game.threshold * 100}%`;
    enterPhase("countdown");
  }
}

function tickCountdown(now, face, blink) {
  const left = 3 - Math.floor((now - game.phaseStart) / 1000);
  if (left > 0) return setStatus(String(left), true);
  enterPhase("playing");
  game.startTime = now;
  game.closedSince = null;
  game.faceLostSince = null;
  game.beat = false;
  els.player.classList.add("is-playing");
  setStatus("시작! 눈을 감으면 집니다", true);
}

function tickPlaying(now, face, blink) {
  const elapsed = now - game.startTime;
  renderTimer(elapsed);

  if (!face) {
    game.closedSince = null;
    game.faceLostSince ??= now;
    if (now - game.faceLostSince >= CONFIG.faceLostLimitMs) {
      return finish(game.faceLostSince - game.startTime, "face");
    }
    return;
  }
  game.faceLostSince = null;

  if (blink >= game.threshold) {
    game.closedSince ??= now;
    if (now - game.closedSince >= CONFIG.closedHoldMs) {
      return finish(game.closedSince - game.startTime, "blink");
    }
  } else {
    game.closedSince = null;
  }

  if (!game.beat && elapsed > CONFIG.opponentRecordMs) {
    game.beat = true;
    els.timer.classList.add("beat");
    els.progressFill.classList.add("beat");
    setStatus("상대 기록 돌파! 계속 버텨서 랭킹을 올리세요", true);
  } else if (elapsed > 3000 && !game.beat) {
    setStatus(`상대 기록까지 ${formatGap(CONFIG.opponentRecordMs - elapsed)}`);
  }
}

async function finish(timeMs, reason) {
  if (game.phase !== "playing") return;
  game.phase = "over";
  stopCamera();
  timeMs = Math.max(0, timeMs);

  document.body.classList.remove("flash");
  void document.body.offsetWidth;
  document.body.classList.add("flash");

  const win = timeMs > CONFIG.opponentRecordMs;
  const reasonText = {
    blink: "눈을 감았어요",
    face: "얼굴이 화면에서 벗어났어요",
    hidden: "게임 화면을 벗어났어요",
  }[reason];

  els.resultEyebrow.textContent = reasonText;
  els.resultTitle.textContent = win ? "승리!" : "패배";
  els.resultTitle.classList.toggle("win", win);
  els.resultTime.textContent = formatTime(timeMs);
  els.resultDesc.textContent = win
    ? `상대의 기록을 ${formatGap(timeMs - CONFIG.opponentRecordMs)} 넘겼어요.`
    : `상대 기록 1:20.00까지 ${formatGap(CONFIG.opponentRecordMs - timeMs)} 모자랐어요.`;
  els.resultError.textContent = "";
  show("result");

  const record = { nickname: game.nickname, time_ms: Math.round(timeMs) };
  if (timeMs >= 1000) {
    try {
      await submitScore(record.nickname, record.time_ms);
    } catch (err) {
      els.resultError.textContent = err.message;
    }
  } else {
    els.resultError.textContent = "1초 미만 기록은 랭킹에 등록되지 않아요.";
  }
  renderBoard(els.boardResult, record);
}

function abort(message) {
  game.phase = "over";
  stopCamera();
  els.startError.textContent = message ?? "";
  show("start");
  renderBoard(els.boardStart);
}

function stopCamera() {
  cancelAnimationFrame(game.rafId);
  game.stream?.getTracks().forEach((t) => t.stop());
  game.stream = null;
  els.video.srcObject = null;
  els.player.classList.remove("is-playing");
}

// ---------------- HUD ----------------
function setStatus(text, big = false) {
  els.status.textContent = text;
  els.status.classList.toggle("big", big);
}

function renderTimer(ms) {
  els.timer.textContent = formatTime(ms);
  // 트랙 전체 = 상대 기록의 1.25배 → 상대 기록이 80% 지점
  const pct = Math.min(100, (ms / (CONFIG.opponentRecordMs * 1.25)) * 100);
  els.progressFill.style.width = `${pct}%`;
}

function updateMeter(face, blink) {
  els.meterFill.style.width = `${face ? blink * 100 : 0}%`;
  const closing = face && blink >= game.threshold;
  els.meterFill.classList.toggle("warn", closing);
  els.eyeState.textContent = !face ? "얼굴 없음" : closing ? "눈 감김!" : "눈 뜸";
  els.eyeState.className = `eye-state ${!face || closing ? "warn" : "open"}`;
}

function resetHud() {
  game.phase = "idle";
  renderTimer(0);
  els.timer.classList.remove("beat");
  els.progressFill.classList.remove("beat");
  els.meterFill.style.width = "0";
  els.eyeState.textContent = "준비 중";
  els.eyeState.className = "eye-state";
}

// ---------------- 이벤트 ----------------
els.startForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const name = els.nickname.value.trim().replace(/\s+/g, " ");
  if (!name || name.length > 12) {
    els.startError.textContent = "닉네임은 1~12자로 입력해 주세요.";
    return;
  }
  saveNickname(name);
  startGame(name);
});

$("btn-quit").addEventListener("click", () => abort());
$("btn-retry").addEventListener("click", () => startGame(game.nickname));
$("btn-home").addEventListener("click", () => {
  show("start");
  renderBoard(els.boardStart);
});

// 탭을 숨기면 감지가 멈추므로, 진행 중이면 그 시점에 종료
document.addEventListener("visibilitychange", () => {
  if (document.hidden && game.phase === "playing") {
    finish(performance.now() - game.startTime, "hidden");
  } else if (document.hidden && (game.phase === "calibrating" || game.phase === "countdown")) {
    abort("게임 화면을 벗어나서 중단됐어요.");
  }
});

// 상대 사진이 없으면 자리표시자
const markNoPhoto = () => els.opponent.classList.add("no-photo");
els.opponentImg.addEventListener("error", markNoPhoto);
if (els.opponentImg.complete && els.opponentImg.naturalWidth === 0) markNoPhoto();

els.nickname.value = loadNickname();
els.boardMode.textContent = isOnline ? "온라인" : "이 기기에만 저장됨";
renderBoard(els.boardStart);
