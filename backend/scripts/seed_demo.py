import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.db import init_db
from src.services.seed import seed_demo
init_db(); seed_demo(); print('seed_demo completed idempotently')
