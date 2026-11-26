"""같은 프로그램이 두 번 켜지는 것을 막는다.

여러 개가 동시에 돌면 말풍선이 각자 떠서 화면에 겹쳐 보인다.
(윈도우 전용. 다른 OS에서는 그냥 통과한다.)
"""
import sys

ERROR_ALREADY_EXISTS = 183
_handles = []  # 프로세스가 살아 있는 동안 뮤텍스를 잡고 있어야 한다


def ensure_single(name):
    """이미 같은 이름으로 떠 있으면 조용히 종료한다."""
    if not sys.platform.startswith("win"):
        return
    import ctypes

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, f"Local\\1day1project.{name}")
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        sys.exit(0)
    _handles.append(handle)
