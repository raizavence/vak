#!/usr/bin/env python3
"""Vāk — वाक् — Publica no blog quando Raíza confirma. Nada mais."""

import base64
import hashlib
import hmac
import json
import logging
import os
import sqlite3
import time
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN  = os.getenv("TELEGRAM_TOKEN")
GHOST_URL       = os.getenv("GHOST_URL", "https://raizavenceslau.com.br")
GHOST_ADMIN_KEY = os.getenv("GHOST_ADMIN_KEY", "")
SHISHYA_DB_PATH = os.getenv("SHISHYA_DB_PATH", "/root/shishya/memoria.db")
TIMEZONE        = ZoneInfo("America/Sao_Paulo")
DB_PATH         = os.path.join(os.path.dirname(__file__), "memoria.db")

CONFIRMAR = {"sim","s","yes","ok","pode","vai","bora","claro","isso","manda","positivo","confirmar","confirma","confirmado","com certeza","é isso","isso mesmo","quero","aceito","aceitar","aceita","tá","ta","blz","beleza","certo","correto"}
CANCELAR  = {"não","nao","n","no","cancela","cancelar","cancelado"}

def match(text: str, variants: set) -> bool:
    tokens = text.lower().strip().rstrip(".,!?").split()
    return bool(variants.intersection(tokens)) or any(v in text.lower() for v in variants if " " in v)

def match_exact(text: str, variants: set) -> bool:
    # Ação destrutiva: só dispara se a mensagem inteira for uma das variantes
    # — espelhado em shishya/bot.py (match_exact)
    return text.lower().strip().rstrip(".,!? ") in variants

# ─── BANCO ────────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS config (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
        """)

def get_config(key, default=None):
    with get_db() as conn:
        row = conn.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

def set_config(key, value):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            (key, str(value) if value is not None else "")
        )

# ─── GHOST API ────────────────────────────────────────────────────────────────

def ghost_token():
    if not GHOST_ADMIN_KEY or ":" not in GHOST_ADMIN_KEY:
        raise ValueError("GHOST_ADMIN_KEY inválida.")
    key_id, secret = GHOST_ADMIN_KEY.split(":", 1)
    iat = int(time.time())
    exp = iat + 300
    header  = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT", "kid": key_id}).encode()).rstrip(b"=")
    payload = base64.urlsafe_b64encode(json.dumps({"iat": iat, "exp": exp, "aud": "/admin/"}).encode()).rstrip(b"=")
    signing = header + b"." + payload
    sig     = base64.urlsafe_b64encode(
        hmac.new(bytes.fromhex(secret), signing, hashlib.sha256).digest()
    ).rstrip(b"=")
    return (signing + b"." + sig).decode()

def ghost_request(method, path, body=None):
    url = f"{GHOST_URL}/ghost/api/admin{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Ghost {ghost_token()}",
            "Content-Type": "application/json",
            "Accept-Version": "v5.0",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req) as resp:
            if resp.status == 204:
                return {}
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Ghost API {e.code}: {e.read().decode()}")

def texto_para_lexical(texto: str) -> str:
    if not texto:
        return json.dumps({"root": {"children": [], "direction": None, "format": "", "indent": 0, "type": "root", "version": 1}})
    if texto.strip().startswith("{") and '"root"' in texto:
        return texto
    paragrafos = [p.strip() for p in texto.split("\n\n") if p.strip()]
    if not paragrafos:
        paragrafos = [p.strip() for p in texto.split("\n") if p.strip()]
    children = [
        {"children": [{"detail": 0, "format": 0, "mode": "normal", "style": "", "text": p, "type": "text", "version": 1}],
         "direction": "ltr", "format": "", "indent": 0, "type": "paragraph", "version": 1}
        for p in paragrafos
    ]
    return json.dumps({"root": {"children": children, "direction": "ltr", "format": "", "indent": 0, "type": "root", "version": 1}})

def criar_post(titulo: str, conteudo: str, subtitulo: str = "") -> dict:
    post_data = {
        "title": titulo,
        "lexical": texto_para_lexical(conteudo),
        "status": "published",
        "tags": [],
    }
    if subtitulo:
        post_data["custom_excerpt"] = subtitulo
    data = ghost_request("POST", "/posts/", {"posts": [post_data]})
    return data["posts"][0]

# ─── INTEGRAÇÃO SHISHYA ───────────────────────────────────────────────────────

def listar_rascunhos_shishya() -> list:
    try:
        conn = sqlite3.connect(SHISHYA_DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, rascunho FROM semanas WHERE estado = 'autorizado' ORDER BY id DESC LIMIT 1"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Erro ao ler banco do Shishya: {e}")
        return []

def marcar_shishya_descartado(semana_id: int):
    try:
        conn = sqlite3.connect(SHISHYA_DB_PATH)
        conn.execute(
            "UPDATE semanas SET estado = 'descartado' WHERE id = ?",
            (semana_id,)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Erro ao descartar rascunho no Shishya: {e}")

def marcar_shishya_publicado(semana_id: int, post_url: str):
    try:
        conn = sqlite3.connect(SHISHYA_DB_PATH)
        conn.execute(
            "UPDATE semanas SET estado = 'publicado', post_url = ? WHERE id = ?",
            (post_url, semana_id)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Erro ao atualizar banco do Shishya: {e}")

def montar_pendente(row: dict) -> tuple:
    # CONTRATO pendente: {titulo, subtitulo, conteudo, semana_id} — espelhado em shishya/bot.py:804
    draft = json.loads(row["rascunho"])
    payload = {
        "titulo": draft.get("titulo", ""),
        "subtitulo": draft.get("subtitulo", ""),
        "conteudo": draft.get("conteudo", ""),
        "semana_id": row["id"],
    }
    preview = f"*{payload['titulo']}*"
    if payload["subtitulo"]:
        preview += f"\n_{payload['subtitulo']}_"
    return payload, preview

# ─── HANDLERS ─────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    existing = get_config("owner_chat_id")
    if existing and existing != chat_id:
        return
    set_config("owner_chat_id", chat_id)
    await update.message.reply_text("Vāk presente.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    owner_id = get_config("owner_chat_id")
    if not owner_id or str(update.effective_chat.id) != owner_id:
        return

    text = update.message.text.strip()
    pendente_raw = get_config("pendente", "")

    # Há publicação pendente — aguardando sim/não
    if pendente_raw:
        if match_exact(text, CANCELAR):
            if get_config("cancelar_confirmar") == "1":
                pendente = json.loads(pendente_raw)
                semana_id = pendente.get("semana_id")
                if semana_id:
                    marcar_shishya_descartado(int(semana_id))
                set_config("pendente", "")
                set_config("cancelar_confirmar", "")
                await update.message.reply_text("Cancelado.")
            else:
                set_config("cancelar_confirmar", "1")
                await update.message.reply_text("Tem certeza? Responda *não* ou *cancelar* de novo para confirmar — isso é irreversível.", parse_mode="Markdown")
            return

        if match(text, CONFIRMAR):
            pendente = json.loads(pendente_raw)
            set_config("pendente", "")
            set_config("cancelar_confirmar", "")
            try:
                post = criar_post(
                    titulo=pendente["titulo"],
                    conteudo=pendente["conteudo"],
                    subtitulo=pendente.get("subtitulo", ""),
                )
                semana_id = pendente.get("semana_id")
                if semana_id:
                    marcar_shishya_publicado(int(semana_id), post.get("url", ""))
                await update.message.reply_text(f"Publicado: {post.get('url', '')}")
            except Exception as e:
                await update.message.reply_text(f"Erro ao publicar: {e}")
            return

        # Outra mensagem enquanto há pendente — ignora e lembra
        await update.message.reply_text("Tem uma publicação aguardando. Responde *sim* para publicar ou *não* para cancelar.", parse_mode="Markdown")
        return

    # Verifica fila do Shishya
    rascunhos = listar_rascunhos_shishya()
    if rascunhos:
        payload, preview = montar_pendente(rascunhos[0])
        set_config("pendente", json.dumps(payload, ensure_ascii=False))
        await update.message.reply_text(
            f"{preview}\n\nVocê quer fazer essa publicação?",
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text("Nenhum texto aguardando publicação.")

# ─── NOTIFICAÇÃO EXTERNA (chamada pelo Shishya via token) ─────────────────────

async def cmd_notificar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shishya chama isso quando autoriza um rascunho."""
    owner_id = get_config("owner_chat_id")
    if not owner_id or str(update.effective_chat.id) != owner_id:
        return
    rascunhos = listar_rascunhos_shishya()
    if not rascunhos:
        await update.message.reply_text("Nenhum rascunho autorizado encontrado.")
        return
    payload, preview = montar_pendente(rascunhos[0])
    set_config("pendente", json.dumps(payload, ensure_ascii=False))
    await update.message.reply_text(
        f"{preview}\n\nVocê quer fazer essa publicação?",
        parse_mode="Markdown"
    )

# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    init_db()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("notificar", cmd_notificar))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Vāk iniciada.")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
