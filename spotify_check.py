import os
import sys
from urllib.parse import urlparse

import spotipy
from dotenv import load_dotenv
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import SpotifyOAuth


load_dotenv()

client_id = os.getenv("SPOTIFY_CLIENT_ID")
client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")
scope = "playlist-read-private playlist-read-collaborative"

if not client_id or not client_secret:
    raise SystemExit("Faltan SPOTIFY_CLIENT_ID y SPOTIFY_CLIENT_SECRET en .env")

if len(sys.argv) != 2:
    raise SystemExit("Uso: python spotify_check.py <url_playlist_spotify>")

parts = [part for part in urlparse(sys.argv[1]).path.split("/") if part]
if len(parts) < 2 or parts[0] != "playlist":
    raise SystemExit("Pasa una URL de playlist de Spotify.")

spotify = spotipy.Spotify(
    auth_manager=SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=scope,
        cache_path=".spotify_cache",
        open_browser=False,
        show_dialog=True,
    )
)

me = spotify.current_user()
print(f"Cuenta autorizada: {me.get('display_name')} <{me.get('email')}>")

try:
    playlist = spotify.playlist(parts[1])
    print(f"Playlist: {playlist['name']}")
    print(f"Owner: {playlist['owner']['display_name']}")
    print(f"Publica: {playlist.get('public')}")
    print(f"Canciones: {playlist['tracks']['total']}")

    items = spotify.playlist_items(
        parts[1],
        fields="items(track(name,artists(name))),next",
        additional_types=("track",),
        limit=5,
    )
    for idx, item in enumerate(items["items"], start=1):
        track = item.get("track")
        if not track:
            continue
        artists = ", ".join(artist["name"] for artist in track["artists"])
        print(f"{idx}. {artists} - {track['name']}")
except SpotifyException as exc:
    print(f"Spotify error: HTTP {exc.http_status} - {exc.msg}")
    print("Si es 403, esa cuenta no tiene acceso API a esa playlist o faltan permisos.")
    raise SystemExit(1)
