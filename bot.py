#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube → Telegram Bot
Descarga videos de YouTube y los sube a Telegram con barra de progreso futurista.

Uso:
    1) pip install -r requirements.txt
    2) Crea un bot en @BotFather en Telegram, copia el TOKEN
    3) Establece TOKEN como variable de entorno: export BOT_TOKEN="tu_token"
       (o edita la línea de abajo)
    4) python bot.py
"""

import os
import re
import time
import threading
from pathlib import Path
import subprocess
import logging

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction

# Configuración
BOT_TOKEN = os.getenv("BOT_TOKEN", "AQUI_VA_TU_TOKEN")
if BOT_TOKEN == "AQUI_VA_TU_TOKEN":
    raise ValueError("❌ Establece BOT_TOKEN como variable de entorno o edita bot.py")

logging.basicConfig(level=logging.WARNING)

# Carpetas
DOWNLOADS_DIR = Path("descargas")
DOWNLOADS_DIR.mkdir(exist_ok=True)

# Estado de descargas
downloads = {}

# --------------------------------------------------------------------------
# Símbolos futuristas
# --------------------------------------------------------------------------
SYMBOLS = {
    "loading": ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"],
    "pulse": ["◐", "◓", "◑", "◒"],
    "bar": "█",
    "empty": "░",
    "sparkle": "✨",
    "rocket": "🚀",
    "download": "⬇️",
    "upload": "⬆️",
    "play": "▶️",
    "gear": "⚙️",
    "flash": "⚡",
    "check": "✅",
    "error": "❌",
    "clock": "⏱️",
    "fire": "🔥",
}


def fmt_size(bytes_val):
    """Formatea bytes a MB/GB."""
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_val < 1024:
            return f"{bytes_val:.1f}{unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f}TB"


def fmt_time(seconds):
    """Formatea segundos a mm:ss."""
    mins, secs = divmod(int(seconds), 60)
    return f"{mins}:{secs:02d}"


def progress_bar(percent, width=20):
    """Barra de progreso futurista."""
    filled = int(percent / 100 * width)
    empty = width - filled
    return SYMBOLS["bar"] * filled + SYMBOLS["empty"] * empty


def anim_frame(phase):
    """Devuelve un símbolo animado según el frame."""
    return SYMBOLS["loading"][phase % len(SYMBOLS["loading"])]


def is_valid_youtube_url(url):
    """Valida que sea un URL de YouTube."""
    patterns = [
        r"(youtube\.com|youtu\.be)",
    ]
    return any(re.search(p, url, re.I) for p in patterns)


# --------------------------------------------------------------------------
# Descarga con progreso
# --------------------------------------------------------------------------
def download_video(url, user_id, update_callback):
    """
    Descarga video con yt-dlp y callback de progreso.
    Devuelve (ruta_archivo, duracion, titulo) o (None, None, None) si falla.
    """
    output_template = str(DOWNLOADS_DIR / f"{user_id}_%(title)s.%(ext)s")

    def progress_hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0:
                pct = (downloaded / total) * 100
                speed = d.get("_speed_str", "...")
                eta = d.get("_eta_str", "...")
                update_callback(
                    status="descargando",
                    percent=pct,
                    downloaded=downloaded,
                    total=total,
                    speed=speed,
                    eta=eta,
                )
        elif d["status"] == "finished":
            update_callback(status="procesando", percent=100)

    cmd = [
        "yt-dlp",
        "-f", "best[ext=mp4]/best",
        "-o", output_template,
        "--no-warnings",
        "--quiet",
        url,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            return None, None, None

        # Busca el archivo descargado
        files = sorted(DOWNLOADS_DIR.glob(f"{user_id}_*"), key=lambda p: p.stat().st_mtime, reverse=True)
        if files:
            filepath = files[0]
            size = filepath.stat().st_size
            update_callback(status="listo", percent=100, filesize=size)
            
            # Intenta extraer duración
            duration = "desconocida"
            try:
                cmd2 = ["yt-dlp", "--print", "duration", url]
                dur_result = subprocess.run(cmd2, capture_output=True, text=True, timeout=10)
                if dur_result.returncode == 0:
                    try:
                        duration = fmt_time(float(dur_result.stdout.strip()))
                    except:
                        pass
            except:
                pass

            title = filepath.stem.replace(str(user_id) + "_", "")
            return str(filepath), duration, title

        return None, None, None
    except subprocess.TimeoutExpired:
        return None, None, None
    except Exception:
        return None, None, None


# --------------------------------------------------------------------------
# Handlers del bot
# --------------------------------------------------------------------------
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Comando /start."""
    user = update.effective_user
    text = (
        f"{SYMBOLS['rocket']} **Bienvenido, {user.first_name}**\n\n"
        f"Soy un bot que descarga videos de YouTube y los sube a Telegram.\n\n"
        f"**¿Cómo funciona?**\n"
        f"1️⃣ Envíame un link de YouTube\n"
        f"2️⃣ Descargaré el video\n"
        f"3️⃣ Te lo subiré con barra de progreso futurista\n\n"
        f"**Comandos:**\n"
        f"/help — instrucciones\n"
        f"/status — estado actual\n\n"
        f"🎬 Adelante, ¡envíame un link!"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Comando /help."""
    text = (
        f"{SYMBOLS['sparkle']} **Guía rápida**\n\n"
        f"**Soporto:**\n"
        f"• YouTube.com\n"
        f"• youtu.be\n"
        f"• Videos públicos\n\n"
        f"**Limitaciones:**\n"
        f"• Tamaño máx: 2 GB (límite de Telegram)\n"
        f"• Duración máx: ~ 2 horas (depende del servidor)\n\n"
        f"**Ejemplo:**\n"
        f"`https://www.youtube.com/watch?v=dQw4w9WgXcQ`\n\n"
        f"Usa `/status` para ver qué se está descargando ahora."
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def status_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Comando /status."""
    user_id = update.effective_user.id
    if user_id not in downloads:
        await update.message.reply_text(f"{SYMBOLS['check']} Sin descargas en progreso.")
        return

    d = downloads[user_id]
    status = d.get("status", "pendiente")
    percent = d.get("percent", 0)
    bar = progress_bar(percent)
    phase = int(time.time() * 4) % 10
    anim = anim_frame(phase)

    text = (
        f"{anim} **Estado actual**\n\n"
        f"Status: {status.upper()}\n"
        f"Progreso: {percent:.0f}%\n"
        f"`{bar}`\n"
    )

    if "speed" in d:
        text += f"Velocidad: {d['speed']}\n"
    if "eta" in d:
        text += f"Tiempo restante: {d['eta']}\n"
    if "downloaded" in d and "total" in d:
        text += f"Descargado: {fmt_size(d['downloaded'])} / {fmt_size(d['total'])}\n"

    await update.message.reply_text(text, parse_mode="Markdown")


async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Maneja URLs de YouTube."""
    user = update.effective_user
    user_id = user.id
    message = update.message
    text = message.text or ""

    if not is_valid_youtube_url(text):
        await message.reply_text(
            f"{SYMBOLS['error']} No reconozco ese link. "
            f"¿Es de YouTube? Intenta: `/help`",
            parse_mode="Markdown"
        )
        return

    # Inicia descarga
    status_msg = await message.reply_text(
        f"{anim_frame(0)} {SYMBOLS['download']} Analizando video...",
        parse_mode="Markdown"
    )

    phase = [0]

    def update_progress(status, percent=0, **kwargs):
        downloads[user_id] = {
            "status": status,
            "percent": percent,
            **kwargs
        }

    async def animated_update():
        """Actualiza el mensaje cada 0.5s con animación."""
        last_update = time.time()
        while user_id in downloads and downloads[user_id].get("status") != "listo":
            now = time.time()
            if now - last_update < 0.5:
                await asyncio.sleep(0.1)
                continue

            d = downloads.get(user_id, {})
            status = d.get("status", "pendiente")
            percent = d.get("percent", 0)
            bar = progress_bar(percent)
            phase[0] = (phase[0] + 1) % 10
            anim = anim_frame(phase[0])

            icon = (
                SYMBOLS["download"] if status == "descargando"
                else SYMBOLS["gear"] if status == "procesando"
                else SYMBOLS["upload"] if status == "subiendo"
                else SYMBOLS["loading"][phase[0] % 10]
            )

            txt = f"{anim} **{status.upper()}** {percent:.0f}%\n`{bar}`"
            if "speed" in d:
                txt += f"\nVelocidad: {d['speed']}"
            if "eta" in d:
                txt += f" | ETA: {d['eta']}"
            if "downloaded" in d and "total" in d:
                txt += f"\n{fmt_size(d['downloaded'])} / {fmt_size(d['total'])}"

            try:
                await status_msg.edit_text(txt, parse_mode="Markdown")
            except:
                pass

            last_update = now
            await asyncio.sleep(0.1)

    import asyncio

    # Descarga en thread
    def download_thread():
        filepath, duration, title = download_video(text, user_id, update_progress)

        if not filepath:
            asyncio.run_coroutine_threadsafe(
                status_msg.edit_text(
                    f"{SYMBOLS['error']} No se pudo descargar. "
                    f"¿Es un video público? Intenta otro link.",
                    parse_mode="Markdown"
                ),
                ctx.application.bot.get_session()
            )
            downloads.pop(user_id, None)
            return

        updates_task = asyncio.run_coroutine_threadsafe(
            animated_update(),
            ctx.application.bot.get_session()
        )

        # Sube a Telegram
        try:
            asyncio.run_coroutine_threadsafe(
                status_msg.edit_text(
                    f"{anim_frame(0)} {SYMBOLS['upload']} Subiendo a Telegram... 0%\n"
                    f"`{progress_bar(0)}`",
                    parse_mode="Markdown"
                ),
                ctx.application.bot.get_session()
            )

            with open(filepath, "rb") as video:
                asyncio.run_coroutine_threadsafe(
                    message.reply_video(
                        video=video,
                        caption=(
                            f"{SYMBOLS['check']} {SYMBOLS['fire']} **{title}**\n\n"
                            f"Duración: {duration} | Tamaño: {fmt_size(Path(filepath).stat().st_size)}\n"
                            f"{SYMBOLS['rocket']} Descargado y subido con éxito"
                        ),
                        parse_mode="Markdown"
                    ),
                    ctx.application.bot.get_session()
                )

            asyncio.run_coroutine_threadsafe(
                status_msg.delete(),
                ctx.application.bot.get_session()
            )

            # Limpia archivo
            Path(filepath).unlink()
            downloads.pop(user_id, None)

        except Exception as e:
            asyncio.run_coroutine_threadsafe(
                status_msg.edit_text(
                    f"{SYMBOLS['error']} Error al subir: {str(e)[:100]}",
                    parse_mode="Markdown"
                ),
                ctx.application.bot.get_session()
            )
            downloads.pop(user_id, None)

    thread = threading.Thread(target=download_thread, daemon=True)
    thread.start()


async def error_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Maneja errores."""
    pass


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    print("\n" + "=" * 60)
    print(f"  {SYMBOLS['rocket']} Bot de YouTube → Telegram")
    print(f"  {SYMBOLS['sparkle']} Iniciando...")
    print("=" * 60 + "\n")

    app.run_polling()


if __name__ == "__main__":
    main()
