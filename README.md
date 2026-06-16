# Vāk — Porta de Publicação do Blog

Bot Telegram que publica posts no Ghost. — वाक् —

Recebe rascunhos já revisados (enviados pelo Shishya), apresenta o título à autora e aguarda confirmação. Se aprovado, publica no Ghost exatamente como está. Sem edição, sem sugestões, sem IA de texto — só a porta entre o rascunho e o blog.

---

## Tecnologias

- Python 3.10+
- python-telegram-bot
- Ghost Admin API

## Configuração

Copie `.env.example` para `.env` e preencha:

```
TELEGRAM_TOKEN=
GHOST_URL=
GHOST_ADMIN_API_KEY=
```

## Execução

```bash
pip install -r requirements.txt
python bot.py
```

Ou via systemd: `sudo systemctl start vak`
