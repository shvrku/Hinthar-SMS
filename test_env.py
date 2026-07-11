import os
from pathlib import Path
from dotenv import load_dotenv, dotenv_values

BASE_DIR = Path(__file__).resolve().parent
env_path = BASE_DIR / '.env'
print(f"BASE_DIR: {BASE_DIR}")
print(f"env_path: {env_path}")
print(f"env_path.exists(): {env_path.exists()}")
if env_path.exists():
    print("env_path contents:")
    print(env_path.read_text())
    print("dotenv_values(env_path):", dotenv_values(env_path))
print("Before load_dotenv, os.getenv('DATABASE_URL'):", repr(os.getenv('DATABASE_URL')))
load_dotenv(env_path, override=True)
print("After load_dotenv, os.getenv('DATABASE_URL'):", repr(os.getenv('DATABASE_URL')))


