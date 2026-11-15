"""Resolve teacher-facing answer names to repository TXT files."""

def puzzle_surface(path):
    text = path.read_text(encoding='utf-8-sig')
    if '【謎面】' in text and '【湯底】' in text:
        surface = text.split('【謎面】', 1)[1].split('【湯底】', 1)[0].strip()
        if surface:
            return surface
    raise ValueError('新題目 TXT 需包含【謎面】與【湯底】')


def resolve_puzzle(directory, answer):
    answer = answer.strip()
    if not answer or any(c in answer for c in '/\\:') or answer in ('.', '..'):
        raise ValueError('題目名稱不正確')
    filename = answer if answer.lower().endswith('.txt') else answer + '.txt'
    directory = directory.resolve()
    matches = [p for p in directory.iterdir() if p.is_file() and p.name.casefold() == filename.casefold()]
    if len(matches) != 1 or matches[0].resolve().parent != directory:
        raise ValueError('找不到唯一的題目檔案')
    return matches[0]
