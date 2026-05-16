# Bot de musica para Discord

Bot sencillo para Raspberry Pi con comandos slash:

- `/play <url o busqueda>`
- `/pause`
- `/resume`
- `/skip`
- `/queue`
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
git clone REPO_URL discord-music-bot
cd discord-music-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
```

Pon tu token en `DISCORD_TOKEN`.

Opcional pero recomendado: en Discord, activa el modo desarrollador, copia el ID de tu servidor y ponlo en `GUILD_ID`. Asi los comandos slash suelen aparecer al instante.

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
