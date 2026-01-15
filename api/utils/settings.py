from pydantic import BaseSettings

class Settings(BaseSettings):
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str
    POSTGRES_PORT: int
    DATABASE_URL: str
    
    LLM_MODEL: str
    LLM_URL: str
    
    class Config: 
        env_file = ".env" # Api ja carrega automaticamente
        
        
settings = Settings()