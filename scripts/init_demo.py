"""Create synthetic demo data only. Real student data never lives in this file."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

if __name__ == '__main__':
    private = ROOT / 'private'
    private.mkdir(exist_ok=True)
    files = {
        'roster.json': [{'classroom': '999', 'seat': '01', 'password': '12345'}],
        'puzzles.json': [{
            'id': 'practice-01', 'version': '1', 'title': '沒有下雨的雨傘',
            'surface': '晴朗的下午，小晴在教室裡打開雨傘。\n老師看見了，不但沒有阻止，還請大家向她說謝謝。\n\n這是怎麼一回事？',
            'solution': '這是班級的光與影實驗。小晴依老師指示撐開不透光的雨傘，遮住照向桌面的燈光，讓同學觀察影子。她沒有淋雨，也沒有違反規定。',
            'facts': ['地點是教室。', '老師事先請她協助光與影實驗。', '傘用來遮擋燈光。', '當天沒有下雨。', '雨傘顏色與解題無關。'],
            'max_turns': 30, 'enabled': True,
            'mock_cases': {'她是不是在做實驗': 'yes', '當時有沒有下雨': 'no', '雨傘的顏色是不是關鍵': 'irrelevant', '她是不是在幫忙老師': 'yes'},
            'mock_examples': [{'question': '她是不是在做實驗？', 'type': 'is'}, {'question': '當時有沒有下雨？', 'type': 'has'}, {'question': '雨傘的顏色是不是關鍵？', 'type': 'is'}]
        }]
    }
    for name, data in files.items():
        path = private / name
        if not path.exists():
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    env = private / 'local.env'
    if not env.exists():
        env.write_text((ROOT / '.env.example').read_text(encoding='utf-8'), encoding='utf-8')
    print('已建立本機示範設定；既有私密資料不覆寫。範例題僅供測試，正式題庫請另行設定。')
