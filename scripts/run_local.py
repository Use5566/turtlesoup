"""Run the local sandbox only; no deployments or external writes by default."""
import os
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
from dotenv import load_dotenv
load_dotenv(ROOT / 'private/local.env')
import uvicorn

if __name__ == '__main__':
    if os.getenv('APP_MODE', 'local') != 'local':
        raise SystemExit('本機啟動器只允許 APP_MODE=local')
    uvicorn.run('backend.app:create_app', factory=True, host='127.0.0.1',
                port=int(os.getenv('PORT', '8765')), workers=1, access_log=False)
