import os
import asyncio
import logging

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.members = True  # necessário para resolver menções de membros nos comandos

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user} (id: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"🔄 {len(synced)} comandos slash sincronizados.")
    except Exception as e:
        print(f"Erro ao sincronizar comandos: {e}")


async def main():
    if not TOKEN:
        raise RuntimeError(
            "Defina a variável de ambiente DISCORD_TOKEN (veja .env.example)."
        )
    async with bot:
        await bot.load_extension("cogs.game_cog")
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
