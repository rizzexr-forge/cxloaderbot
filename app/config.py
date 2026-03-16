import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    bot_token: str = Field(..., alias='TOKEN')
    admin_id: int = Field(..., alias='ADMIN')
    use_local_server: bool = Field(False, alias='USE_LOCAL_SERVER')
    local_server_url: str = Field('http://localhost:8081', alias='LOCAL_SERVER_URL')
    db_host: str = Field('localhost', alias='DB_HOST')
    db_port: int = Field(3306, alias='DB_PORT')
    db_name: str = Field('certaxbot', alias='DB_NAME')
    db_user: str = Field('certaxbot', alias='DB_USER')
    db_pass: str = Field('', alias='DB_PASS')
    
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'),
        env_file_encoding='utf-8',
        extra='ignore'
    )

config = Settings()
