# Festival Quintal dos Sabores — Site + Painel Admin

Site institucional do festival, agora com um **painel administrativo** para gerenciar
as atrações da seção "Quem faz o Quintal acontecer" (foto ou vídeo do YouTube).

---

## Arquivos

| Arquivo | O que é |
|---|---|
| `server.py` | Servidor (Python, só biblioteca padrão) — serve o site, o admin e a API. |
| `quintal-sabores.html` | O site em si (uma página, com lightbox no carrossel e atrações dinâmicas). |
| `admin.html` | Painel administrativo (login + CRUD das atrações). |
| `atracoes.json` | Banco de dados das atrações (editado pela API; não mexer à mão). |
| `assets/logo.png` | Logotipo (extraído do base64 original). |
| `uploads/` | Imagens enviadas pelo painel (criado automaticamente). |

---

## Como rodar localmente

```bash
cd /home/user
python3 server.py
```

- **Site:** http://localhost:8000/
- **Admin:** http://localhost:8000/admin
- **Senha do admin (padrão):** `quintal2026`

Para trocar a senha e a porta:

```bash
ADMIN_PASSWORD=minha-senha PORT=8000 python3 server.py
```

---

## Usando o painel admin

1. Acesse `/admin` e entre com a senha.
2. Clique em **"+ Nova atração"**.
3. Preencha:
   - **Nome** (ex.: BANDA DO ZÉ PELIM)
   - **Tag/selo** (ex.: Headliner, Sábado, Cultural)
   - **Subtítulo** (ex.: Sábado · 21h · Palco Principal)
   - **Mídia**: escolha **Foto** (cole a URL de uma imagem **ou** envie um arquivo
     do computador) **ou** **Vídeo** (cole um link do YouTube — `watch?v=`,
     `youtu.be`, `shorts` ou `embed`).
   - **Destaque**: marca o card grande no topo da grade.
4. Clique em **Salvar**. A seção "Atrações" do site atualiza automaticamente
   (basta recarregar a página).

Também é possível **editar**, **excluir** e **reordenar** (setas ↑↓) as atrações.

---

## Como os dados fluem

```
admin.html ──(login, CRUD via API)──▶ server.py ──▶ atracoes.json
                                                       │
site (quintal-sabores.html) ◀── GET /api/atracoes ─────┘
```

- O site busca `GET /api/atracoes` e renderiza os cards.
- Se a API não estiver acessível (ex.: abrindo o HTML direto com `file://`),
  o site mantém os cards estáticos originais como fallback.

---

## API

| Método | Rota | Descrição |
|---|---|---|
| `GET`  | `/api/atracoes` | Lista as atrações da edição ativa (ou passe `?edicao=YYYY`). |
| `GET`  | `/api/edicoes` | Lista todas as edições do festival (ano, status, subtítulo). |
| `GET`  | `/api/programacao` | Lista a programação por dias e horários (público). |
| `GET`  | `/api/secoes` | Lista os textos editáveis das seções (público). |
| `POST` | `/api/login` | `{ "senha": "..." }` → retorna `{ "token": ... }` ou `429` em bloqueio por rate limit. |
| `POST` | `/api/atracoes` | Cria atração (requer `X-Admin-Token`). |
| `PUT`  | `/api/atracoes/<id>` | Atualiza atração (requer token). |
| `DELETE` | `/api/atracoes/<id>` | Remove atração (requer token). |
| `POST` | `/api/edicoes` | Cadastra nova edição (requer token). |
| `PUT`  | `/api/edicoes` | Atualiza a lista completa de edições (requer token). |
| `PUT`  | `/api/edicoes/arquivar` | Arquiva edições anteriores e ativa a informada (requer token). |
| `PUT`  | `/api/programacao` | Atualiza a programação completa (requer token; valida schema). |
| `PUT`  | `/api/secoes` | Atualiza os textos das seções (requer token; valida schema). |
| `POST` | `/api/upload` | `{ "data": "data:image/...;base64,..." }` → retorna URL pública do Supabase Storage. |

---

## Publicação (deploy)

O site tem dados dinâmicos, então precisa de uma hospedagem que **rode o Python**
(servidor sempre ligado). Opções:

- **Render** (gratuito): serviço tipo "Web Service", comando `python3 server.py`.
- **Railway / Fly.io / Heroku**: idem.
- **VPS** (DigitalOcean, AWS, etc.): `nohup python3 server.py &` + proxy reverso (nginx/Caddy).

Não funciona em hospedagem 100% estática (GitHub Pages, Netlify, Zyrosite) — nesses
casos o site abriria, mas as atrações ficariam no fallback estático e o admin não
funcionaria.

### Observações de segurança e arquitetura

- **Banco de Dados Supabase (PostgreSQL)**:
  - O backend conecta-se diretamente à API REST do Supabase via a biblioteca padrão do Python (`urllib.request`), sem dependências externas (`pip`).
  - **Segurança de Chaves e Gateway**: A `SUPABASE_SERVICE_KEY` reside exclusivamente nas variáveis de ambiente do backend (`.env`). Nenhuma chave ou URL do Supabase é exposta no HTML/cliente. O site e o admin continuam comunicando-se estritamente através dos endpoints `/api/...` do servidor.
  - **Políticas RLS no PostgreSQL**: O acesso direto via chave anon/publishable possui permissão estrita de apenas `SELECT` (leitura). Ações de alteração de dados (`INSERT`, `UPDATE`, `DELETE`) requerem a `service_role` key mantida no servidor.
  - **Fallback Somente-Leitura de Emergência**: Caso haja instabilidade na conexão com o Supabase, o servidor utiliza os arquivos JSON locais (`atracoes.json`, `programacao.json`, `secoes.json`) como cache de emergência para manter o site 100% online.
  - **Seeding Idempotente**: Ao iniciar com tabelas do Supabase vazias, o servidor realiza o seed inicial dos dados padrão uma única vez (verificando o marcador `secoes.id='main'`), sem nunca duplicar registros ou sobrescrever modificações.
- **Rate Limiting no Login**: Máximo de **5 tentativas falhas por IP** em uma janela de **15 minutos**. Ao exceder, o servidor retorna HTTP `429` informando o tempo restante em minutos e a contagem regressiva em segundos.
  *Nota de arquitetura*: O controle de rate limit e tokens é mantido em memória (`failed_logins` e `tokens`), sendo indicado para execuções em **instância única / processo único**.
- **Gestão de Sessão e Timeouts**:
  - **Inatividade no Cliente (`admin.html`)**: O painel efetua logout automático após **15 minutos** sem interação (movimento de mouse, digitação, clique ou toque).
  - **Expiração no Servidor (`server.py`)**: O token de acesso expira após **30 minutos** de inatividade. O timestamp de última atividade é atualizado a cada requisição válida.
- **Proteção Anti-XSS**: Todos os textos vindos do painel administrativo são tratados estritamente como texto puro e são escapados (`esc()` ou `.textContent`) antes da renderização no site público.
- **Validação de Schema nos Endpoints `PUT`**: As requisições de atualização da programação (`PUT /api/programacao`) e textos (`PUT /api/secoes`) passam por validação de formato e tipagem no backend, retornando `400 Bad Request` caso o payload esteja malformado.

---

## Pendências opcionais

- Conectar a newsletter a um serviço de e-mail (hoje é só visual).
- Preencher URLs de YouTube/TikTok/Facebook no rodapé (só o Instagram está real).
- Ajustar URL canônica e `og:image` no `<head>` do site para o domínio real.

---

## Passagem de bastão (continuar o trabalho em outro agente/IDE)

Esta seção reúne todo o contexto para um novo agente (ex.: Antigravity) dar
continuidade ao projeto sem precisar reconstruir o raciocínio.

### Contexto geral
- Projeto: site de evento "Festival Quintal dos Sabores" (festival gastronômico
  da periferia de Belo Horizonte).
- Stack: **HTML/CSS/JS vanilla + backend Python puro** (biblioteca padrão, sem
  dependências). Não usar frameworks.
- Idioma: tudo em **português (pt-BR)** — código, comentários, textos e UI.

### O que já está pronto (preservar, não refazer)
1. Site visualmente completo (hero, sobre, pilares, galeria/carrossel, atrações,
   experiências, gastronomia, inscrição, programação, edições, newsletter,
   apoiadores, footer).
2. **Lightbox** no carrossel "O Festival em Imagens": clique abre modal ampliado
   com navegação (‹ ›), contador, legenda, fechar por Esc/clique no fundo,
   suporte a teclado e restauração de foco.
3. **Painel admin** (`admin.html`) para gerir as atrações: criar/editar/excluir/
   reordenar; mídia = **foto** (URL ou upload) **ou vídeo do YouTube** (aceita
   `watch?v=`, `youtu.be`, `shorts`, `embed`); campo de destaque (card grande);
   prévia antes de salvar.
4. Seção de atrações no site renderizada via `GET /api/atracoes`, com **fallback
   estático** quando a API não responde.
5. **API REST**: `GET /api/atracoes`, `POST /api/login`, `POST/PUT/DELETE
   /api/atracoes/<id>`, `POST /api/upload` (base64 → `/uploads/`).
6. Acessibilidade e SEO: semântica (header/main/footer), skip link, meta
   description, Open Graph, Twitter Card, favicon, JSON-LD de Event,
   `loading="lazy"`, `:focus-visible`.

### Decisões já tomadas (respeitar)
- Dados em arquivo JSON (`atracoes.json`), não em banco de dados.
- Autenticação do admin: **senha fixa + token em memória** (simples, de propósito).
- Vídeo do YouTube **incorporado direto no card** (player dentro do card).
- Identidade visual fixa: amarelo `#F5B800`, vermelho `#C0392B`, preto `#1A1208`,
  fundo `#FEFCF5`; fontes **Bebas Neue + Inter**.

### Próximas etapas sugeridas (propor ordem e confirmar antes de grandes mudanças)
1. Expandir o painel admin para editar também a **programação** (horários dos
   dois dias) e os **textos das seções**.
2. Melhorar a segurança do login (rate limiting básico + logout automático).

### Como testar (após qualquer mudança)
```bash
python3 server.py
# em outro terminal:
curl -s http://localhost:8000/api/atracoes
TOKEN=$(curl -s -X POST http://localhost:8000/api/login -H 'Content-Type: application/json' -d '{"senha":"quintal2026"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
# CRUD, upload e validação de URL do YouTube...
```

---

## Prompt simples para continuar (copiar e colar)

> Continue desenvolvendo o site "Festival Quintal dos Sabores" (festival
> gastronômico de Belo Horizonte). Leia primeiro o `README.md` — ele tem todo o
> contexto, a lista de arquivos, como rodar e o que já está pronto.
>
> Stack: HTML/CSS/JS vanilla + Python puro (sem dependências), tudo em pt-BR.
>
> Para rodar: `python3 server.py` → site em http://localhost:8000/ e admin em
> http://localhost:8000/admin (senha: `quintal2026`).
>
> Não refaça o que já existe (site completo, lightbox no carrossel, painel admin
> das atrações com foto ou vídeo do YouTube, API REST, acessibilidade/SEO).
>
> Próximas etapas sugeridas: permitir editar a programação e os textos das seções
> pelo admin; melhorar a segurança do login. Confirme comigo antes de grandes
> mudanças.

