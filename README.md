# Bot de musica para Discord

Bot sencillo para Raspberry Pi con comandos slash:

- `/play <url o busqueda>`
- `/pause`
- `/resume`
- `/skip`
- `/queue`
- `/shuffle`
- `/spotify_connect`
- `/spotify_connect_stop`
- `/spotify_devices`
- `/jam`
- `/stop`
- `/leave`

## 1. Crear el bot en Discord

1. Entra en <https://discord.com/developers/applications>.
2. Crea una aplicacion y entra en **Bot**.
3. Pulsa **Reset Token** y copia el token.
4. En **OAuth2 > URL Generator**, marca:
   - `bot`
   - `applications.commands`
5. En permisos del bot, marca:
   - `Connect`
   - `Speak`
   - `Send Messages`
   - `Use Slash Commands`
6. Abre la URL generada e invita el bot a tu servidor.

## 2. Instalar en Raspberry Pi

```bash
sudo apt update
sudo apt install -y git python3 python3-venv ffmpeg
git clone https://github.com/Alexlose2/discord-music-bot.git discord-music-bot
cd discord-music-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
```

Pon tu token en `DISCORD_TOKEN`.

Opcional pero recomendado: en Discord, activa el modo desarrollador, copia el ID de tu servidor y ponlo en `GUILD_ID`. Asi los comandos slash suelen aparecer al instante.

Para usar enlaces de Spotify, crea una app en <https://developer.spotify.com/dashboard> y pon tambien:

```env
SPOTIFY_CLIENT_ID=tu_client_id
SPOTIFY_CLIENT_SECRET=tu_client_secret
MAX_SPOTIFY_TRACKS=50
```

Spotify se usa para leer titulos. El audio se busca y reproduce desde YouTube.

Para playlists privadas, anade tambien:

```env
SPOTIFY_USE_USER_AUTH=true
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback
```

En la app de Spotify Developer, en **Redirect URIs**, anade exactamente:

```text
http://127.0.0.1:8888/callback
```

Despues ejecuta una vez:

```bash
rm -f .spotify_cache
python spotify_login.py
```

Abre la URL que salga, acepta, copia la URL final a la que te manda el navegador y pegala en la terminal si te la pide. Eso guarda un archivo local `.spotify_cache`.

Si Spotify devuelve `403 Forbidden`, entra en tu app de Spotify Developer y revisa **User Management**. En apps en modo desarrollo, anade el email de la cuenta de Spotify que va a autorizar el bot.

Si ya habias hecho login antes y actualizas el bot, vuelve a autorizar para aceptar permisos de reproduccion:

```bash
rm -f .spotify_cache
python spotify_login.py
```

## Spotify Connect experimental

El bot tambien puede intentar actuar como salida de Spotify Connect dentro del canal de voz. Es experimental, requiere Spotify Premium y usa `librespot`.

Instala `librespot` en la Raspberry:

```bash
sudo apt update
sudo apt install -y cargo build-essential libasound2-dev pkg-config
cargo install librespot
echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

Opcionalmente pon el nombre del dispositivo en `.env`:

```env
SPOTIFY_CONNECT_DEVICE_NAME=Discord Raspberry
SPOTIFY_CONNECT_DEVICE_TIMEOUT=60
```

Arranca el bot y usa:

```text
/spotify_connect
```

El bot intentara transferir tu Spotify a `Discord Raspberry` y empezar a reproducir solo. Tambien puedes decirle con que empezar:

```text
/spotify_connect spotify_url:https://open.spotify.com/playlist/...
```

Si quieres solo abrir el altavoz sin darle play automaticamente:

```text
/spotify_connect reproducir:false
```

Para pararlo:

```text
/spotify_connect_stop
```

Si no aparece en Spotify, reinicia el bot y comprueba que `librespot --version` funciona en la Raspberry.

Si el bot no consigue iniciar la musica solo, usa:

```text
/spotify_devices
```

Ese comando muestra que dispositivos ve la API de Spotify en tu cuenta. Si `Discord Raspberry` no sale ahi, abre Spotify una vez y selecciona manualmente `Discord Raspberry`; despues vuelve a probar `/spotify_connect`.

Spotify no ofrece API publica para crear una Jam automaticamente. Si quieres que el bot mande un enlace de Jam, crea la Jam en Spotify, copia el enlace y ponlo en `.env`:

```env
SPOTIFY_JAM_LINK=https://spotify.link/tu-jam
```

Luego usa:

```text
/jam
```

## 3. Arrancar

```bash
source venv/bin/activate
python bot.py
```

Si todo va bien veras:

```text
Bot conectado como NombreDelBot
```

## 4. Dejarlo encendido con systemd

Crea el servicio:

```bash
sudo nano /etc/systemd/system/discord-music-bot.service
```

Pega esto:

```ini
[Unit]
Description=Discord Music Bot
After=network-online.target

[Service]
WorkingDirectory=/home/pi/discord-music-bot
ExecStart=/home/pi/discord-music-bot/venv/bin/python /home/pi/discord-music-bot/bot.py
Restart=always
RestartSec=5
User=pi

[Install]
WantedBy=multi-user.target
```

Activalo:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now discord-music-bot
sudo systemctl status discord-music-bot
```

## Actualizar yt-dlp

Si YouTube deja de funcionar:

```bash
cd ~/discord-music-bot
source venv/bin/activate
pip install -U yt-dlp
sudo systemctl restart discord-music-bot
```
