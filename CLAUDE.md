# CLAUDE.md — Projeto Vāk

## O que a Vāk é agora

Vāk — वाक् — é a porta de publicação. Uma função só: receber um texto já revisado e perguntar a Raíza se pode publicar no blog.

Não edita. Não sugere. Não debate. Não usa GPT. Não tem agente.

**Fluxo completo:**
1. Shishya autoriza um rascunho → notifica a Vāk
2. Vāk mostra o título (e subtítulo se houver) e pergunta: "Você quer fazer essa publicação?"
3. Raíza responde "sim" → Vāk publica no Ghost exatamente como está
4. Raíza responde "não" → cancelado, rascunho descartado

Toda revisão de texto acontece antes — no Shishya junto com o Claude Code. O que chega à Vāk já está pronto.

---

## Arquitetura

### Stack
- **Linguagem:** Python 3.10
- **Bot:** python-telegram-bot 22.7 (async)
- **Blog:** Ghost Admin API v6 (só criação de post)
- **Banco:** SQLite (`memoria.db`) — config + pendente
- **Deploy:** systemd (`vak.service`)
- **Sem OpenAI** — GPT removido completamente

### Arquivos
```
vak/
├── bot.py          # toda a lógica
├── memoria.db      # banco (gerado ao iniciar)
├── requirements.txt
├── .env
├── vak.service
└── CLAUDE.md
```

### Variáveis de ambiente (`.env`)
```
TELEGRAM_TOKEN=
GHOST_URL=https://raizavenceslau.com.br
GHOST_ADMIN_KEY=     # key_id:secret da integração Ghost Admin API
SHISHYA_DB_PATH=/root/shishya/memoria.db
```

---

## O que a Vāk NÃO faz (definitivo)

- Não edita texto
- Não sugere alterações
- Não debate design editorial
- Não lista posts, não gerencia tags, não muda configurações
- Não usa LLM de nenhum tipo
- Não age por iniciativa própria além de mostrar o rascunho pendente

---

## Ghost Admin API

- **Auth:** JWT gerado com `GHOST_ADMIN_KEY` (formato `key_id:secret`)
- **Operação única:** `POST /posts/` com `status: published`
- Conteúdo convertido para formato Lexical (Ghost v6) via `texto_para_lexical()`

---

## Integração com o Shishya

- Vāk lê o banco do Shishya diretamente (`semanas WHERE estado = 'autorizado'`)
- Após publicar, marca `estado = 'publicado'` e salva a URL no Shishya
- Shishya notifica Vāk via `/notificar` (comando Telegram)

---

## Ecossistema

- [[project-shishya]] — gera e autoriza o conteúdo
- [[project-ghost-blog]] — o blog onde tudo é publicado
- [[project-jiva]] — bot separado, logística do grupo de estudos

---

## 2026-09-11 — Fix: `texto_para_lexical()` não renderizava links markdown

Post "A sede que sempre esteve comigo" (gerado pelo Shri Shankara, agente do professor Jonas, fora do fluxo Shishya→Vāk) tinha links em `[texto](url)` no meio do texto. `texto_para_lexical()` só sabia gerar parágrafos de texto puro — os colchetes apareceriam literalmente no post, nunca tinha sido notado porque nenhum post anterior tinha link.

**Fix:** nova função `_texto_nodes()` faz parse de `[texto](url)` dentro de cada parágrafo via regex e monta os nós `link`/`text` do Lexical corretamente intercalados (`MARKDOWN_LINK_RE`). `texto_para_lexical()` agora chama `_texto_nodes(p)` em vez de gerar um nó de texto único por parágrafo. Retrocompatível — parágrafo sem link continua saindo como um nó de texto simples.

**Publicação desse post:** como não veio autorizado via `semanas` (não passou pelo Shishya), publiquei direto via Ghost Admin API — mas como **rascunho** (`status: draft`) primeiro, pra Raíza conferir a formatação real no tema (link de preview `{GHOST_URL}/p/{uuid}/`) antes de aprovar. Só virou `published` depois do "sim" explícito dela, com várias rodadas de edição no meio (ela relendo e mandando trechos pra trocar, uma PUT por rodada usando `updated_at` atual pra evitar conflito otimista da API). Pode valer como padrão pra qualquer texto que chegue pronto fora do fluxo Shishya.
