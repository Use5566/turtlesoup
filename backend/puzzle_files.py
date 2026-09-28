"""Resolve teacher-facing answer names to repository TXT files."""
ALIASES = {'麟角腹足海螺': '海螺.TXT'}


def resolve_puzzle(directory, answer):
    answer = answer.strip()
    if not answer or any(c in answer for c in '/\\:') or answer in ('.', '..'):
        raise ValueError('題目名稱不正確')
    filename = ALIASES.get(answer, answer if answer.lower().endswith('.txt') else answer + '.txt')
    directory = directory.resolve()
    matches = [p for p in directory.iterdir() if p.is_file() and p.name.casefold() == filename.casefold()]
    if len(matches) != 1 or matches[0].resolve().parent != directory:
        raise ValueError('找不到唯一的題目檔案')
    return matches[0]
