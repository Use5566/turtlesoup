"""Build only public frontend assets. Never copies backend, private, or work."""
import json
import os
from pathlib import Path
import shutil
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]

def build(api_url):
    parsed = urlparse(api_url)
    if api_url and (parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError('API 網址必須是公開 HTTPS 網址，不可含憑證、查詢或片段')
    target = ROOT / 'docs'
    target.mkdir(exist_ok=True)
    for source in (ROOT / 'web').iterdir():
        if source.is_file() and source.suffix in ('.html', '.css', '.js', '.svg'):
            shutil.copyfile(source, target / source.name)
    (target / 'config.js').write_text('window.TURTLESOUP_CONFIG = ' + json.dumps({'apiBase': api_url.rstrip('/')}) + ';\n', encoding='utf-8')
    (target / '.nojekyll').touch()
    print('前台已輸出至 docs/；不包含後端或私密檔案。')
    if not api_url:
        print('後端網址尚未提供，前台顯示尚未連線，不能登入。')

if __name__ == '__main__':
    api_url = os.environ.get('TURTLESOUP_API_URL')
    if api_url is None:
        config = ROOT / 'docs/config.js'
        if config.exists():
            raw = config.read_text(encoding='utf-8').split('=', 1)[1].strip().rstrip(';')
            api_url = json.loads(raw)['apiBase']
    build(api_url or '')
