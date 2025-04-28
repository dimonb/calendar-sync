import os
from dotenv import load_dotenv

def load_env():
    env_path = os.getenv('ENV_PATH', '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)