import os

from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth


load_dotenv()

client_id = os.getenv("SPOTIFY_CLIENT_ID")
client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")
scope = "playlist-read-private playlist-read-collaborative"

if not client_id or not client_secret:
    raise SystemExit("Faltan SPOTIFY_CLIENT_ID y SPOTIFY_CLIENT_SECRET en .env")

auth = SpotifyOAuth(
    client_id=client_id,
    client_secret=client_secret,
    redirect_uri=redirect_uri,
    scope=scope,
    cache_path=".spotify_cache",
    open_browser=False,
)

token = auth.get_access_token(as_dict=True)

if not token:
    raise SystemExit("No he podido guardar el token de Spotify.")

print("Spotify autorizado. Ya puedes arrancar el bot.")
