from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', env_prefix='CARTO_', extra='ignore')
    storage: Path = ROOT / 'storage'
    data: Path = ROOT / 'data'
    ollama_url: str = 'http://127.0.0.1:11434'
    ollama_model: str = 'qwen2.5vl:7b'
    ollama_timeout: float = 120
    ollama_concurrency: int = 1
    invite_code: str = ''
    secure_cookies: bool = False
    allowed_origins: str = ''
    max_upload_mb: int = 8
    rules_path: Path = ROOT / 'config/rules.json'
    auto_import: bool = True

settings = Settings()
settings.storage.mkdir(parents=True, exist_ok=True)
