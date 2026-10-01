import asyncio
from tools.parser_101evler import DEMO_PROPERTIES
from tools.database import init_db, add_property

async def run():
    await init_db()
    for p in DEMO_PROPERTIES:
        await add_property(p)
    print("DB Seeded successfully.")

asyncio.run(run())
