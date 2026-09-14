"""Read-only check. Prints headers/counts, never passwords or roster contents."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / 'private/local.env')
from backend.config import Settings
from backend.sheets import GoogleSheets
from backend.roster import Roster

if __name__ == '__main__':
    settings = Settings.from_env()
    settings.roster_mode = 'google'
    google = GoogleSheets(settings)
    try:
        meta = google.metadata()
        print('試算表：', meta['properties']['title'])
        print('分頁：', [(x['properties']['sheetId'], x['properties']['title']) for x in meta['sheets']])
        roster = Roster(settings, google)
        roster.refresh()
        print('名冊格式驗證通過；學生筆數：', len(roster.cache))
    except Exception as exc:
        print('檢查未通過：', str(exc))
        sys.exit(1)
