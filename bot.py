import asyncio
import os
import random
import traceback
from collections import deque
from dataclasses import dataclass
from urllib.parse import urlparse

import discord
import spotipy
import yt_dlp
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth


load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_USE_USER_AUTH = os.getenv("SPOTIFY_USE_USER_AUTH", "false").lower() == "true"
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")
MAX_SPOTIFY_TRACKS = int(os.getenv("MAX_SPOTIFY_TRACKS", "50"))
SPOTIFY_SCOPE = "playlist-read-private playlist-read-collaborative"

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
spotify_client: spotipy.Spotify | None = None

if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET and SPOTIFY_USE_USER_AUTH:
    spotify_client = spotipy.Spotify(
        auth_manager=SpotifyOAuth(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET,
            redirect_uri=SPOTIFY_REDIRECT_URI,
            scope=SPOTIFY_SCOPE,
            cache_path=".spotify_cache",
            open_browser=False,
            show_dialog=True,
        )
    )
elif SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
    spotify_client = spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET,
        )
    )


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
        self.shuffle = False
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


def is_spotify_url(query: str) -> bool:
    parsed = urlparse(query)
    return parsed.netloc in {"open.spotify.com", "www.open.spotify.com"}


def spotify_type_and_id(url: str) -> tuple[str, str]:
    parts = [part for part in urlparse(url).path.split("/") if part]
    for index, part in enumerate(parts):
        if part in {"track", "album", "playlist"} and index + 1 < len(parts):
            return part, parts[index + 1]
    raise RuntimeError("No reconozco ese enlace de Spotify.")


def spotify_track_query(track: dict) -> str | None:
    if not track or track.get("is_local") or track.get("type") not in {None, "track"}:
        return None

    artists = ", ".join(artist["name"] for artist in track.get("artists", []))
    title = track.get("name")
    if not title:
        return None

    return f"{artists} - {title} audio"


def spotify_queries_from_url(url: str) -> list[str]:
    if not spotify_client:
        raise RuntimeError(
            "Faltan SPOTIFY_CLIENT_ID y SPOTIFY_CLIENT_SECRET en el archivo .env"
        )

    spotify_type, spotify_id = spotify_type_and_id(url)
    queries: list[str] = []

    if spotify_type == "track":
        track = spotify_client.track(spotify_id)
        query = spotify_track_query(track)
        return [query] if query else []

    if spotify_type == "album":
        album = spotify_client.album(spotify_id)
        album_artists = ", ".join(artist["name"] for artist in album.get("artists", []))
        for item in album["tracks"]["items"][:MAX_SPOTIFY_TRACKS]:
            artists = ", ".join(artist["name"] for artist in item.get("artists", [])) or album_artists
            queries.append(f"{artists} - {item['name']} audio")
        return queries

    if spotify_type == "playlist":
        results = spotify_client.playlist_items(spotify_id, additional_types=("track",), limit=100)

        while results and len(queries) < MAX_SPOTIFY_TRACKS:
            for item in results["items"]:
                if len(queries) >= MAX_SPOTIFY_TRACKS:
                    break
                track = item.get("track") or item.get("item")
                query = spotify_track_query(track)
                if query:
                    queries.append(query)

            results = spotify_client.next(results) if results.get("next") else None

        return queries

    raise RuntimeError("Solo soporto enlaces de cancion, album o playlist de Spotify.")


async def spotify_queries(url: str) -> list[str]:
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, lambda: spotify_queries_from_url(url))
    except SpotifyException as exc:
        if exc.http_status == 401:
            raise RuntimeError(
                "Spotify pide autorizacion de usuario para esa playlist. "
                "Pon SPOTIFY_USE_USER_AUTH=true y ejecuta python spotify_login.py"
            ) from exc
        if exc.http_status == 404:
            raise RuntimeError(
                "No encuentro esa playlist. Si es privada, activa SPOTIFY_USE_USER_AUTH."
            ) from exc
        if exc.http_status == 403:
            raise RuntimeError(
                "Spotify ha denegado acceso a esa playlist. Borra .spotify_cache, "
                "ejecuta python spotify_login.py otra vez, y comprueba en Spotify Developer "
                "que tu usuario esta anadido en User Management si la app esta en modo desarrollo."
            ) from exc
        raise


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

        if state.shuffle and len(state.queue) > 1:
            song_index = random.randrange(len(state.queue))
            song = state.queue[song_index]
            del state.queue[song_index]
        else:
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
@app_commands.describe(busqueda="URL de YouTube/SoundCloud/Spotify o texto para buscar")
async def play(interaction: discord.Interaction, busqueda: str) -> None:
    guild_id = require_guild(interaction)
    await interaction.response.defer(thinking=True)
    state = bot.state_for(guild_id)

    if is_spotify_url(busqueda):
        try:
            queries = await spotify_queries(busqueda)
        except Exception as exc:
            await interaction.followup.send(f"No he podido leer Spotify: `{exc}`")
            return

        if not queries:
            await interaction.followup.send(
                "No he encontrado canciones reproducibles en ese enlace de Spotify. "
                "Si la playlist tiene canciones, actualiza con `git pull` y prueba "
                "`python spotify_check.py \"URL_DE_LA_PLAYLIST\"` en la Raspberry."
            )
            return

        voice_client = await ensure_voice(interaction)
        await interaction.followup.send(
            f"He encontrado {len(queries)} canciones en Spotify. Buscandolas en YouTube..."
        )

        added = 0
        failed = 0
        should_start = not voice_client.is_playing() and not voice_client.is_paused()

        for query in queries:
            try:
                song = await extract_song(query, interaction.user.display_name)
            except Exception:
                failed += 1
                continue

            state.queue.append(song)
            added += 1

            if should_start:
                should_start = False
                await play_next(interaction.guild, interaction.channel)

        message = f"Anadidas {added} canciones desde Spotify."
        if failed:
            message += f" No pude preparar {failed}."
        await interaction.followup.send(message)
        return

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

    lines = [f"Modo aleatorio: **{'activado' if state.shuffle else 'desactivado'}**"]
    if state.current:
        lines.append(f"Ahora: **{state.current.title}**")

    if state.queue:
        lines.extend(f"{idx}. {song.title}" for idx, song in enumerate(state.queue, start=1))

    if len(lines) == 1:
        await interaction.response.send_message("La cola esta vacia.", ephemeral=True)
        return

    await interaction.response.send_message("\n".join(lines[:11]))


@bot.tree.command(name="shuffle", description="Activa o desactiva el modo aleatorio.")
@app_commands.describe(activar="Dejalo vacio para alternar el modo actual")
async def shuffle(interaction: discord.Interaction, activar: bool | None = None) -> None:
    guild_id = require_guild(interaction)
    state = bot.state_for(guild_id)

    if activar is None:
        state.shuffle = not state.shuffle
    else:
        state.shuffle = activar

    status = "activado" if state.shuffle else "desactivado"
    await interaction.response.send_message(f"Modo aleatorio {status}.")


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
