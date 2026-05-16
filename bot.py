import asyncio
import os
import traceback
from collections import deque
from dataclasses import dataclass

import discord
import yt_dlp
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv


load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "default_search": "ytsearch1",
    "extract_flat": False,
    "source_address": "0.0.0.0",
}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)


@dataclass
class Song:
    title: str
    webpage_url: str
    stream_url: str
    requested_by: str


class MusicState:
    def __init__(self) -> None:
        self.queue: deque[Song] = deque()
        self.current: Song | None = None
        self.lock = asyncio.Lock()


class MusicBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.music_states: dict[int, MusicState] = {}

    async def setup_hook(self) -> None:
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    def state_for(self, guild_id: int) -> MusicState:
        if guild_id not in self.music_states:
            self.music_states[guild_id] = MusicState()
        return self.music_states[guild_id]


bot = MusicBot()


async def extract_song(query: str, requested_by: str) -> Song:
    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))

    if "entries" in data:
        data = data["entries"][0]

    return Song(
        title=data.get("title", "Cancion sin titulo"),
        webpage_url=data.get("webpage_url", query),
        stream_url=data["url"],
        requested_by=requested_by,
    )


def require_guild(interaction: discord.Interaction) -> int:
    if not interaction.guild_id:
        raise app_commands.AppCommandError("Este comando solo funciona dentro de un servidor.")
    return interaction.guild_id


async def ensure_voice(interaction: discord.Interaction) -> discord.VoiceClient:
    if not interaction.user or not isinstance(interaction.user, discord.Member):
        raise app_commands.AppCommandError("No puedo detectar tu canal de voz.")

    voice_state = interaction.user.voice
    if not voice_state or not voice_state.channel:
        raise app_commands.AppCommandError("Metete en un canal de voz primero.")

    voice_client = interaction.guild.voice_client if interaction.guild else None
    if voice_client and voice_client.is_connected():
        if voice_client.channel != voice_state.channel:
            await voice_client.move_to(voice_state.channel)
        return voice_client

    return await voice_state.channel.connect()


async def play_next(guild: discord.Guild, channel: discord.abc.Messageable) -> None:
    state = bot.state_for(guild.id)

    async with state.lock:
        if not state.queue:
            state.current = None
            return

        song = state.queue.popleft()
        state.current = song

    voice_client = guild.voice_client
    if not voice_client or not voice_client.is_connected():
        return

    def after_play(error: Exception | None) -> None:
        if error:
            print(f"Error reproduciendo: {error}")
        asyncio.run_coroutine_threadsafe(play_next(guild, channel), bot.loop)

    try:
        source = discord.FFmpegPCMAudio(song.stream_url, **FFMPEG_OPTIONS)
        voice_client.play(source, after=after_play)
    except Exception as exc:
        traceback.print_exc()
        state.current = None
        await channel.send(f"He entrado al canal, pero no puedo reproducir audio: `{exc}`")
        return

    await channel.send(f"Reproduciendo: **{song.title}**\n<{song.webpage_url}>")


@bot.event
async def on_ready() -> None:
    print(f"Bot conectado como {bot.user}")


@bot.tree.command(name="play", description="Reproduce una URL o busca una cancion.")
@app_commands.describe(busqueda="URL de YouTube/SoundCloud o texto para buscar")
async def play(interaction: discord.Interaction, busqueda: str) -> None:
    guild_id = require_guild(interaction)
    await interaction.response.defer(thinking=True)
    state = bot.state_for(guild_id)

    try:
        song = await extract_song(busqueda, interaction.user.display_name)
    except Exception as exc:
        await interaction.followup.send(f"No he podido preparar esa cancion: `{exc}`")
        return

    voice_client = await ensure_voice(interaction)
    state.queue.append(song)
    await interaction.followup.send(f"Anadida a la cola: **{song.title}**")

    if not voice_client.is_playing() and not voice_client.is_paused():
        await play_next(interaction.guild, interaction.channel)


@bot.tree.command(name="pause", description="Pausa la musica.")
async def pause(interaction: discord.Interaction) -> None:
    voice_client = interaction.guild.voice_client if interaction.guild else None
    if voice_client and voice_client.is_playing():
        voice_client.pause()
        await interaction.response.send_message("Pausado.")
    else:
        await interaction.response.send_message("No hay nada reproduciendose.", ephemeral=True)


@bot.tree.command(name="resume", description="Continua la musica.")
async def resume(interaction: discord.Interaction) -> None:
    voice_client = interaction.guild.voice_client if interaction.guild else None
    if voice_client and voice_client.is_paused():
        voice_client.resume()
        await interaction.response.send_message("Seguimos.")
    else:
        await interaction.response.send_message("No hay nada pausado.", ephemeral=True)


@bot.tree.command(name="skip", description="Salta la cancion actual.")
async def skip(interaction: discord.Interaction) -> None:
    voice_client = interaction.guild.voice_client if interaction.guild else None
    if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
        voice_client.stop()
        await interaction.response.send_message("Saltando cancion.")
    else:
        await interaction.response.send_message("No hay nada que saltar.", ephemeral=True)


@bot.tree.command(name="queue", description="Muestra la cola.")
async def queue(interaction: discord.Interaction) -> None:
    guild_id = require_guild(interaction)
    state = bot.state_for(guild_id)

    lines = []
    if state.current:
        lines.append(f"Ahora: **{state.current.title}**")

    if state.queue:
        lines.extend(f"{idx}. {song.title}" for idx, song in enumerate(state.queue, start=1))

    if not lines:
        await interaction.response.send_message("La cola esta vacia.", ephemeral=True)
        return

    await interaction.response.send_message("\n".join(lines[:11]))


@bot.tree.command(name="stop", description="Para la musica y vacia la cola.")
async def stop(interaction: discord.Interaction) -> None:
    guild_id = require_guild(interaction)
    state = bot.state_for(guild_id)
    state.queue.clear()
    state.current = None

    voice_client = interaction.guild.voice_client if interaction.guild else None
    if voice_client:
        voice_client.stop()

    await interaction.response.send_message("Musica parada y cola vaciada.")


@bot.tree.command(name="leave", description="Saca al bot del canal de voz.")
async def leave(interaction: discord.Interaction) -> None:
    guild_id = require_guild(interaction)
    state = bot.state_for(guild_id)
    state.queue.clear()
    state.current = None

    voice_client = interaction.guild.voice_client if interaction.guild else None
    if voice_client and voice_client.is_connected():
        await voice_client.disconnect()
        await interaction.response.send_message("Me salgo del canal.")
    else:
        await interaction.response.send_message("No estoy en ningun canal de voz.", ephemeral=True)


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
) -> None:
    message = str(error) or "Ha fallado el comando."
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


if not TOKEN:
    raise SystemExit("Falta DISCORD_TOKEN en el archivo .env")

bot.run(TOKEN)
