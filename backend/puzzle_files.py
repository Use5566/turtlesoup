"""Resolve teacher-facing answer names to repository TXT files."""
ALIASES = {'麟角腹足海螺': '海螺.TXT'}

SURFACES = {
    '拳擊蟹': '海底有一隻螃蟹，總是高舉著「兩團東西」走來走去，看起來就像雙手拿著彩球、正在替誰加油一樣。牠沒有在表演，也不是在跳舞，卻因此被人稱為「啦啦隊蟹」。為什麼？',
    '歐氏尖吻鮫': '原本在我們面前的魚，瞬間消失了...',
    '海螺': '在深海採礦時，發現一隻奄奄一息的生鏽海螺。海螺為什麼會生鏽？又為什麼會奄奄一息？',
}


def puzzle_surface(path):
    text = path.read_text(encoding='utf-8-sig')
    if '【謎面】' in text and '【湯底】' in text:
        surface = text.split('【謎面】', 1)[1].split('【湯底】', 1)[0].strip()
        if surface:
            return surface
    if path.stem in SURFACES:
        return SURFACES[path.stem]
    raise ValueError('新題目 TXT 需包含【謎面】與【湯底】')


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
