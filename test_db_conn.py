import asyncio
import aiomysql
from app.config import config

async def test_connection():
    print(f"Attempting to connect to MySQL: {config.db_user}@{config.db_host}:{config.db_port}/{config.db_name}...")
    try:
        conn = await aiomysql.connect(
            host=config.db_host,
            port=config.db_port,
            user=config.db_user,
            password=config.db_pass,
            db=config.db_name,
            autocommit=True
        )
        print("Success! MySQL connection established.")
        async with conn.cursor() as cur:
            await cur.execute("SELECT 1")
            res = await cur.fetchone()
            print(f"Test query result: {res}")
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_connection())
