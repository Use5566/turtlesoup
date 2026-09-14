"""Run explicitly when ready to create two dedicated log tabs. Never alters gid 0."""
import argparse
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / 'private/local.env')
from backend.config import Settings
from backend.sheets import GoogleSheets

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='在指定試算表建立海龜湯專用紀錄分頁')
    parser.add_argument('--create', action='store_true', help='明確執行建立分頁')
    args = parser.parse_args()
    if not args.create:
        parser.error('此操作會建立線上紀錄分頁；準備好後加上 --create')
    GoogleSheets(Settings.from_env()).init_logs()
    print('紀錄分頁已建立；名冊未修改。')
