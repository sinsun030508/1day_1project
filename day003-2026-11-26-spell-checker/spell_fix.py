"""맞춤법 자동 교정기 — 규칙 기반 (1일 1프로젝트)"""
import difflib
import re
import sys
import unicodedata

# 1) 단어 사전: 자주 틀리는 표기 → 표준어
WORDS = {
    "몇일": "며칠", "금새": "금세", "오랫만": "오랜만", "희안": "희한",
    "역활": "역할", "일일히": "일일이", "설겆이": "설거지", "어의없": "어이없",
    "왠만": "웬만", "왠일": "웬일", "웬지": "왠지", "구지": "굳이",
    "깨끗히": "깨끗이", "곰곰히": "곰곰이", "틈틈히": "틈틈이", "꼼꼼이": "꼼꼼히",
    "어떻해": "어떡해", "엇그제": "엊그제", "내노라": "내로라", "됬": "됐",
}

# 2) 정규식 규칙: 문맥이 필요한 것
RULES = [
    (r"되요", "돼요"),                       # 되어요 → 돼요
    (r"되서", "돼서"),
    (r"되도(?!록)", "돼도"),                 # '되도록'은 제외
    (r"안\s?되(?=[.!?]|\s|$)", "안 돼"),     # 문장 끝 '안되' → '안 돼'
    (r"(?<!\S)않(?=\s)", "안"),              # '않 먹어' → '안 먹어'
    (r"지\s?안(?=[아았은는을])", "지 않"),    # '하지안아' → '하지 않아'
]


def has_rieul(ch):
    """한글 음절의 받침이 ㄹ인지 (유니코드 조합 공식)"""
    return (ord(ch) - 0xAC00) % 28 == 8


def correct(text):
    changes = []

    def sub(pattern, repl):
        nonlocal text

        def wrap(m):
            new = repl(m) if callable(repl) else m.expand(repl)
            if new != m.group(0):
                changes.append((m.group(0), new))
            return new

        text = re.sub(pattern, wrap, text)

    for wrong, right in WORDS.items():
        sub(re.escape(wrong), right)
    for pattern, repl in RULES:
        sub(pattern, repl)
    # 3) ㄹ받침 + 께 → 게 ('할께' → '할게', '선생님께'는 유지)
    sub(r"([가-힣])께(?=요|[\s.!?]|$)",
        lambda m: m.group(1) + "게" if has_rieul(m.group(1)) else m.group(0))
    return text, changes


_kiwi = None


def check(text):
    """맞춤법 + 띄어쓰기 교정"""
    global _kiwi
    if _kiwi is None:
        from kiwipiepy import Kiwi  # 형태소 분석기 (첫 호출 때만 로딩)
        _kiwi = Kiwi()
    fixed, changes = correct(text)
    spaced = _kiwi.space(fixed, reset_whitespace=True)
    if spaced != fixed:
        changes.append(("띄어쓰기", "교정"))
    return spaced, changes


# 코드·마크업·주소: 여기에 걸리면 한국어 문장이 아니라고 보고 검사하지 않는다
CODE_LIKE = re.compile(r"https?://|www\.|<[^>]*>|</|/>|```|[`{}]|\[[^\]]*\]\(|=\s*[\"']")
HANGUL = re.compile(r"[가-힣]")
# 마크다운 글머리(`- `, `## `, `1. `)는 본문이 아니므로 떼고 검사한다
LIST_PREFIX = re.compile(r"^\s*(?:[-*+>]|#{1,6}|\d+[.)])\s+")


def strip_prefix(text):
    return LIST_PREFIX.sub("", text)


def looks_like_prose(text, min_ratio=0.4):
    """한국어 문장인지. HTML 태그·링크·코드 줄에 띄어쓰기 교정을 하면 오히려 망가진다."""
    stripped = re.sub(r"\s", "", text)
    if len(stripped) < 2 or CODE_LIKE.search(text):
        return False
    return len(HANGUL.findall(stripped)) / len(stripped) >= min_ratio


def _expand_to_word(text, start, end):
    """바뀐 글자만 집으면 조사 한 글자처럼 보이므로 띄어쓰기 단위까지 넓힌다."""
    while start > 0 and not text[start - 1].isspace():
        start -= 1
    while end < len(text) and not text[end].isspace():
        end += 1
    return start, end


def diff_segments(original, fixed):
    """원문과 교정문을 비교해 바뀐 구간을 찾는다.

    [{"before": 틀린 말, "after": 고친 말, "start": n, "end": m}]
    start/end는 교정문(fixed) 기준 인덱스라, 그대로 잘라서 강조하면 된다.
    """
    merged = []
    for tag, a1, a2, b1, b2 in difflib.SequenceMatcher(None, original, fixed, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        a1, a2 = _expand_to_word(original, a1, a2)
        b1, b2 = _expand_to_word(fixed, b1, b2)
        # 한 단어 안에서 두 군데가 바뀌었거나, '추천 해주는' → '추천해 주는'처럼
        # 원문 범위가 겹치면 한 덩어리로 합친다
        if merged and (b1 <= merged[-1][3] or a1 < merged[-1][1]):
            pa1, pa2, pb1, pb2 = merged[-1]
            merged[-1] = (min(pa1, a1), max(pa2, a2), min(pb1, b1), max(pb2, b2))
        else:
            merged.append((a1, a2, b1, b2))
    # '추천 해주는' → '추천해 주는': 글자가 띄어쓰기를 넘어간 두 덩어리는 합쳐야 띄어쓰기로 읽힌다
    def spacing_only(a1, a2, b1, b2):
        return original[a1:a2].replace(" ", "") == fixed[b1:b2].replace(" ", "")

    i = 0
    while i < len(merged) - 1:
        left, right = merged[i], merged[i + 1]
        joined = (left[0], right[1], left[2], right[3])
        if not spacing_only(*left) and not spacing_only(*right) and spacing_only(*joined):
            merged[i:i + 2] = [joined]
        else:
            i += 1

    segments = []
    for a1, a2, b1, b2 in merged:
        before, after = original[a1:a2], fixed[b1:b2]
        # 글자는 그대로고 띄어쓰기만 달라졌으면 맞춤법 오류와 구분해서 표시한다
        kind = "spacing" if before.replace(" ", "") == after.replace(" ", "") else "spelling"
        segments.append({"before": before, "after": after, "start": b1, "end": b2, "kind": kind})
    return segments


def check_diff(text):
    """교정문과 '어디가 어떻게 바뀌었는지' 목록을 함께 돌려준다."""
    fixed, _ = check(text)
    return fixed, diff_segments(text, fixed)


def mark_line(text, segments, key="before"):
    """틀린 부분 아래에 ^^^ 를 그린 줄 (터미널 표시용).

    맞춤법은 ^, 띄어쓰기는 ~로 구분한다.
    한글은 터미널에서 두 칸을 차지하므로 글자 폭만큼 찍어야 자리가 맞는다.
    """
    hit = [" "] * len(text)
    pos = 0
    for seg in segments:
        found = text.find(seg[key], pos)
        if found < 0:
            continue
        mark = "~" if seg["kind"] == "spacing" else "^"
        for i in range(found, found + len(seg[key])):
            hit[i] = mark
        pos = found + len(seg[key])
    marks = ""
    for ch, mark in zip(text, hit):
        width = 2 if unicodedata.east_asian_width(ch) in "WF" else 1
        marks += mark * width
    return marks.rstrip()


def main():
    lines = [" ".join(sys.argv[1:])] if len(sys.argv) > 1 else iter(lambda: input("> "), "")
    for line in lines:
        fixed, segments = check_diff(line)
        if not segments:
            print("고칠 곳 없음")
            continue
        print("원문:", line)
        print("     ", mark_line(line, segments, "before"))
        print("교정:", fixed)
        print("     ", mark_line(fixed, segments, "after"))
        for seg in segments:
            print(f"  - {seg['before']} → {seg['after']}")


if __name__ == "__main__":
    try:
        main()
    except (EOFError, KeyboardInterrupt):
        pass
