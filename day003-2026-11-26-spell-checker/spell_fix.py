"""맞춤법 자동 교정기 — 규칙 기반 (1일 1프로젝트)"""
import re
import sys

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


def main():
    lines = [" ".join(sys.argv[1:])] if len(sys.argv) > 1 else iter(lambda: input("> "), "")
    for line in lines:
        fixed, changes = check(line)
        print("교정:", fixed)
        for before, after in changes:
            print(f"  - {before} → {after}")


if __name__ == "__main__":
    try:
        main()
    except (EOFError, KeyboardInterrupt):
        pass
