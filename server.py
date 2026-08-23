#!/usr/bin/env python3
"""
Servidor do Festival Quintal dos Sabores
========================================
- Serve o site (quintal-sabores.html), o painel admin (admin.html),
  a pasta /assets e os uploads de imagem (/uploads).
- API REST para gerenciar atrações, programação e textos das seções.
- Autenticação simples por senha + token com expiração por inatividade (30 min)
  e rate limiting no login (5 tentativas por 15 min por IP).
- Persistência em banco de dados Supabase (PostgreSQL / REST API) com fallback
  somente-leitura para arquivos JSON locais em caso de indisponibilidade.

Rodar:
    python3 server.py
    # ou defina a senha e a porta:
    ADMIN_PASSWORD=minhasenha PORT=8000 python3 server.py

Senha padrão do admin: quintal2026  (troque em produção!)
"""
import os
import re
import json
import time
import math
import base64
import secrets
import mimetypes
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote

ROOT = os.path.dirname(os.path.abspath(__file__))

# Carregador simples de variáveis de ambiente do arquivo .env
def load_env():
    env_file = os.path.join(ROOT, ".env")
    if os.path.exists(env_file):
        try:
            with open(env_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip())
        except Exception:
            pass

load_env()

DATA_FILE = os.path.join(ROOT, "atracoes.json")
PROGRAMACAO_FILE = os.path.join(ROOT, "programacao.json")
SECOES_FILE = os.path.join(ROOT, "secoes.json")
EDICOES_FILE = os.path.join(ROOT, "edicoes.json")
UPLOAD_DIR = os.path.join(ROOT, "uploads")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "quintal2026")
PORT = int(os.environ.get("PORT", 8000))

# Credenciais do Supabase (Mantidas estritamente no servidor/backend)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://wowzbcvqfsibkfyjpnbp.supabase.co").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY", "")

TOKEN_TIMEOUT = 30 * 60  # 30 minutos em segundos
RATE_LIMIT_WINDOW = 15 * 60  # 15 minutos em segundos
RATE_LIMIT_MAX = 5

os.makedirs(UPLOAD_DIR, exist_ok=True)

# tokens válidos em memória { token: last_active_timestamp }
tokens = {}

# tentativas de login incorretas { client_ip: [timestamp1, timestamp2, ...] }
failed_logins = {}

MIME_OVERRIDES = {
    ".html": "text/html; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
}

# ---------- Cliente REST Supabase (Python Standard Library) ----------
class SupabaseClient:
    @staticmethod
    def _headers(extra_headers=None):
        h = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"
        }
        if extra_headers:
            h.update(extra_headers)
        return h

    @staticmethod
    def get(table, params=""):
        if not SUPABASE_URL or not SUPABASE_KEY:
            return None
        url = f"{SUPABASE_URL}/rest/v1/{table}"
        if params:
            url += f"?{params}"
        req = urllib.request.Request(url, headers=SupabaseClient._headers(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=5) as res:
                return json.loads(res.read().decode("utf-8"))
        except Exception:
            return None

    @staticmethod
    def upsert(table, data, on_conflict="id"):
        if not SUPABASE_URL or not SUPABASE_KEY:
            return None
        url = f"{SUPABASE_URL}/rest/v1/{table}"
        if on_conflict:
            url += f"?on_conflict={on_conflict}"
        headers = SupabaseClient._headers({
            "Prefer": "resolution=merge-duplicates,return=representation"
        })
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as res:
                return json.loads(res.read().decode("utf-8"))
        except Exception:
            return None

    @staticmethod
    def update_eq(table, field, value, data):
        if not SUPABASE_URL or not SUPABASE_KEY:
            return None
        url = f"{SUPABASE_URL}/rest/v1/{table}?{field}=eq.{urllib.parse.quote(str(value))}"
        headers = SupabaseClient._headers({"Prefer": "return=representation"})
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=headers, method="PATCH")
        try:
            with urllib.request.urlopen(req, timeout=5) as res:
                return json.loads(res.read().decode("utf-8"))
        except Exception:
            return None

    @staticmethod
    def delete_eq(table, field, value):
        if not SUPABASE_URL or not SUPABASE_KEY:
            return None
        url = f"{SUPABASE_URL}/rest/v1/{table}?{field}=eq.{urllib.parse.quote(str(value))}"
        headers = SupabaseClient._headers({"Prefer": "return=representation"})
        req = urllib.request.Request(url, headers=headers, method="DELETE")
        try:
            with urllib.request.urlopen(req, timeout=5) as res:
                return json.loads(res.read().decode("utf-8"))
        except Exception:
            return None

    @staticmethod
    def upload_to_storage(bucket, filename, raw_bytes, content_type="image/png"):
        """Envia bytes brutos para o Supabase Storage e retorna a URL pública, ou None em caso de erro."""
        if not SUPABASE_URL or not SUPABASE_KEY:
            return None
        url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{urllib.parse.quote(filename)}"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": content_type,
            # upsert=true sobrescreve se o nome já existir (sem erro 409)
            "x-upsert": "true",
        }
        req = urllib.request.Request(url, data=raw_bytes, headers=headers, method="PUT")
        try:
            with urllib.request.urlopen(req, timeout=15) as res:
                # Monta URL pública no padrão do Supabase Storage
                public_url = f"{SUPABASE_URL}/storage/v1/object/public/{bucket}/{urllib.parse.quote(filename)}"
                return public_url
        except Exception as e:
            print(f"[Supabase Storage] Erro ao fazer upload: {e}")
            return None



# ---------- Fallback local para JSON ----------
def load_json_file(filepath, default_val):
    if not os.path.exists(filepath):
        return default_val
    try:
        with open(filepath, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default_val


def save_json_file(filepath, data):
    tmp = filepath + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, filepath)


# ---------- Funções de dados (Supabase Primário + Fallback Local) ----------
def load_data():
    sup_data = SupabaseClient.get("atracoes", "select=*&order=created_at.asc")
    if sup_data is not None and isinstance(sup_data, list):
        formatted = []
        for item in sup_data:
            formatted.append({
                "id": item.get("id"),
                "nome": item.get("nome"),
                "tag": item.get("tag") or "",
                "tipo": item.get("tipo") or "",
                "destaque": bool(item.get("destaque")),
                "media": item.get("media") or {},
                "edicao": item.get("edicao") or ""
            })
        return formatted
    return load_json_file(DATA_FILE, [])


def save_data(data):
    save_json_file(DATA_FILE, data)
    records = []
    for item in data:
        records.append({
            "id": item["id"],
            "nome": item["nome"],
            "tag": item.get("tag", ""),
            "tipo": item.get("tipo", ""),
            "destaque": bool(item.get("destaque")),
            "media": item.get("media", {}),
            "edicao": item.get("edicao", "")
        })
    SupabaseClient.upsert("atracoes", records, on_conflict="id")


def load_programacao():
    sup_prog = SupabaseClient.get("programacao", "select=*&order=created_at.asc")
    if sup_prog is not None and isinstance(sup_prog, list):
        formatted = []
        for item in sup_prog:
            formatted.append({
                "id": item.get("id"),
                "dia_num": item.get("dia_num"),
                "dia_nome": item.get("dia_nome"),
                "mes_ano": item.get("mes_ano"),
                "itens": item.get("itens") or []
            })
        return formatted
    return load_json_file(PROGRAMACAO_FILE, [])


def save_programacao(data):
    save_json_file(PROGRAMACAO_FILE, data)
    records = []
    for dia in data:
        records.append({
            "id": dia["id"],
            "dia_num": dia["dia_num"],
            "dia_nome": dia["dia_nome"],
            "mes_ano": dia["mes_ano"],
            "itens": dia.get("itens", [])
        })
    SupabaseClient.upsert("programacao", records, on_conflict="id")


def load_secoes():
    sup_sec = SupabaseClient.get("secoes", "id=eq.main&select=*")
    if sup_sec is not None and isinstance(sup_sec, list) and len(sup_sec) > 0:
        return sup_sec[0].get("dados", {})
    return load_json_file(SECOES_FILE, {})


def save_secoes(data):
    save_json_file(SECOES_FILE, data)
    SupabaseClient.upsert("secoes", [{"id": "main", "dados": data}], on_conflict="id")


def load_edicoes():
    sup_ed = SupabaseClient.get("edicoes", "select=*&order=created_at.asc")
    if sup_ed is not None and isinstance(sup_ed, list):
        formatted = []
        for item in sup_ed:
            formatted.append({
                "id": item.get("id"),
                "ano": item.get("ano"),
                "nome": item.get("nome") or item.get("numero_edicao", ""),
                "subtitulo": item.get("subtitulo"),
                "status": item.get("status")
            })
        return formatted
    return load_json_file(EDICOES_FILE, [])


def save_edicoes(data):
    save_json_file(EDICOES_FILE, data)
    records = []
    for ed in data:
        nome_val = ed.get("nome", "")
        records.append({
            "id": ed["id"],
            "ano": ed.get("ano", ""),
            "nome": nome_val,
            "numero_edicao": nome_val,
            "subtitulo": ed.get("subtitulo", ""),
            "status": ed.get("status", "arquivada")
        })
    SupabaseClient.upsert("edicoes", records, on_conflict="id")


def get_active_edicao_id():
    """Retorna o ID da edição ativa (não mais o ano)."""
    edicoes = load_edicoes()
    for ed in edicoes:
        if ed.get("status") == "ativa":
            return ed.get("id", "")
    return ""


# ---------- Migração de campo edicao (ano → ID) ----------
def _migrate_edicao_field_to_id():
    """Migra atrações que tenham o campo 'edicao' como ano (ex: '2026')
    para apontar para o ID correto da edição (ex: 'ed_2026_6').
    Executa de forma idempotente — ignora registros já migrados."""
    edicoes = load_edicoes()
    if not edicoes:
        return
    # Cria mapeamento ano → ID da edição (usa a primeira edição encontrada p/ aquele ano)
    ano_para_id = {}
    for ed in edicoes:
        ano = ed.get("ano", "")
        if ano and ano not in ano_para_id:
            ano_para_id[ano] = ed["id"]
    # Mapeamento de IDs antigos (edicao-YYYY) → novos IDs
    id_antigo_para_novo = {}
    for ed in edicoes:
        ano = ed.get("ano", "")
        old_id = f"edicao-{ano}"
        if old_id != ed["id"]:
            id_antigo_para_novo[old_id] = ed["id"]

    all_ids = {ed["id"] for ed in edicoes}
    atracoes = load_data()
    updated = False
    for a in atracoes:
        ed_val = a.get("edicao", "")
        if not ed_val or ed_val in all_ids:
            continue  # Já migrado ou vazio
        # Caso 1: edicao é um ano puro (ex: "2026")
        if ed_val in ano_para_id:
            a["edicao"] = ano_para_id[ed_val]
            updated = True
        # Caso 2: edicao é um ID antigo (ex: "edicao-2026")
        elif ed_val in id_antigo_para_novo:
            a["edicao"] = id_antigo_para_novo[ed_val]
            updated = True
    if updated:
        save_data(atracoes)
        print("[Migração] Campo 'edicao' das atrações atualizado de ano/ID antigo → ID da edição.")
    else:
        print("[Migração] Nenhuma atração necessitava de migração de 'edicao'.")


# ---------- Migração automática de imagens locais para o Supabase Storage ----------
def migrate_images_to_supabase_storage():
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    data = load_data()
    changed = False
    for item in data:
        media = item.get("media", {})
        if media and media.get("type") == "photo":
            url = media.get("url", "")
            if url.startswith("/uploads/"):
                filename = url.replace("/uploads/", "")
                local_path = os.path.join(UPLOAD_DIR, filename)
                if os.path.exists(local_path):
                    print(f"[Supabase Storage] Migrando {filename}...")
                    try:
                        with open(local_path, "rb") as f:
                            raw_bytes = f.read()
                        ext = os.path.splitext(filename)[1].lower()
                        ct_map = {".png": "image/png", ".jpg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}
                        content_type = ct_map.get(ext, "image/png")
                        storage_url = SupabaseClient.upload_to_storage("atracoes", filename, raw_bytes, content_type)
                        if storage_url:
                            print(f"[Supabase Storage] Sucesso: {filename} -> {storage_url}")
                            media["url"] = storage_url
                            changed = True
                    except Exception as e:
                        print(f"[Supabase Storage] Erro ao migrar {filename}: {e}")
    if changed:
        save_data(data)
        print("[Supabase Storage] Migração finalizada!")


# ---------- Seeding Idempotente no Supabase ----------
def seed_database_if_needed():
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    # 1. Seeding das seções
    sec_marker = SupabaseClient.get("secoes", "id=eq.main&select=id")
    if sec_marker is not None and isinstance(sec_marker, list) and len(sec_marker) == 0:
        print("[Supabase] Tabela de seções vazia. Realizando seed inicial...")
        local_secoes = load_json_file(SECOES_FILE, {})
        if local_secoes:
            SupabaseClient.upsert("secoes", [{"id": "main", "dados": local_secoes}], on_conflict="id")

        local_atracoes = load_json_file(DATA_FILE, [])
        if local_atracoes:
            records = [{
                "id": a["id"],
                "nome": a["nome"],
                "tag": a.get("tag", ""),
                "tipo": a.get("tipo", ""),
                "destaque": bool(a.get("destaque")),
                "media": a.get("media", {}),
                "edicao": a.get("edicao", "")
            } for a in local_atracoes]
            SupabaseClient.upsert("atracoes", records, on_conflict="id")

        local_prog = load_json_file(PROGRAMACAO_FILE, [])
        if local_prog:
            records = [{
                "id": p["id"],
                "dia_num": p["dia_num"],
                "dia_nome": p["dia_nome"],
                "mes_ano": p["mes_ano"],
                "itens": p.get("itens", [])
            } for p in local_prog]
            SupabaseClient.upsert("programacao", records, on_conflict="id")

    # 2. Seeding das edições se estiver vazio
    ed_marker = SupabaseClient.get("edicoes", "select=id&limit=1")
    if ed_marker is not None and isinstance(ed_marker, list) and len(ed_marker) == 0:
        print("[Supabase] Tabela de edições vazia. Realizando seed inicial...")
        local_ed = load_json_file(EDICOES_FILE, [])
        if local_ed:
            records = [{
                "id": ed["id"],
                "ano": ed.get("ano", ""),
                "nome": ed.get("nome", ed.get("numero_edicao", "")),
                "subtitulo": ed.get("subtitulo", ""),
                "status": ed.get("status", "arquivada")
            } for ed in local_ed]
            SupabaseClient.upsert("edicoes", records, on_conflict="id")
        print("[Supabase] Seed das edições concluído com sucesso!")

    # 3. Migração de dados existentes: atualizar campo 'edicao' das atrações de ano → ID da edição
    _migrate_edicao_field_to_id()


def find_attraction(data, aid):
    for i, a in enumerate(data):
        if a.get("id") == aid:
            return i, a
    return None, None


def read_body(handler):
    length = int(handler.headers.get("Content-Length", 0) or 0)
    if length <= 0:
        return b""
    return handler.rfile.read(length)


def parse_json_body(handler):
    raw = read_body(handler)
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def get_client_ip(handler):
    ff = handler.headers.get("X-Forwarded-For")
    if ff:
        return ff.split(",")[0].strip()
    return handler.client_address[0]


def is_authorized(handler):
    token = handler.headers.get("X-Admin-Token", "")
    if not token or token not in tokens:
        return False
    now = time.time()
    if now - tokens[token] > TOKEN_TIMEOUT:
        del tokens[token]
        return False
    tokens[token] = now
    return True


def validate_attraction(a):
    if not isinstance(a.get("nome"), str) or not a["nome"].strip():
        return "O nome da atração é obrigatório"
    media = a.get("media") or {}
    if media.get("type") not in ("photo", "video"):
        return "Escolha foto ou vídeo"
    if not isinstance(media.get("url"), str) or not media["url"].strip():
        return "A URL da mídia é obrigatória"
    if media["type"] == "video" and not youtube_id(media["url"]):
        return "URL do YouTube inválida"
    return None


def validate_programacao(data):
    if not isinstance(data, list):
        return "A programação deve ser uma lista de dias"
    for dia in data:
        if not isinstance(dia, dict):
            return "Estrutura de dia inválida"
        if not isinstance(dia.get("dia_num"), str) or not isinstance(dia.get("dia_nome"), str) or not isinstance(dia.get("mes_ano"), str):
            return "Campos do dia (dia_num, dia_nome, mes_ano) devem ser texto"
        itens = dia.get("itens")
        if not isinstance(itens, list):
            return "Cada dia deve conter uma lista de horários ('itens')"
        for item in itens:
            if not isinstance(item, dict):
                return "Estrutura de horário inválida"
            if not isinstance(item.get("hora"), str) or not isinstance(item.get("titulo"), str) or not isinstance(item.get("local"), str):
                return "Campos do horário (hora, titulo, local) devem ser texto"
    return None


def validate_secoes(data):
    if not isinstance(data, dict):
        return "A estrutura das seções deve ser um objeto JSON"
    required = {
        "hero": ["eyebrow", "descricao"],
        "sobre": ["titulo", "descricao"],
        "pilares": ["eyebrow", "titulo"],
        "gastronomia": ["eyebrow", "titulo", "descricao"],
        "inscricao": ["titulo", "descricao"],
        "footer": ["marca_texto"]
    }
    for sec, fields in required.items():
        if sec not in data or not isinstance(data[sec], dict):
            return f"Seção '{sec}' ausente ou inválida"
        for f in fields:
            val = data[sec].get(f)
            if not isinstance(val, str):
                return f"Campo '{f}' na seção '{sec}' deve ser texto"
    # Validação opcional: hero.imagens, sobre.imagens, galeria.imagens e experiencias.imagens devem ser listas de strings (URLs)
    for sec_key in ["hero", "sobre", "galeria", "experiencias"]:
        imgs = data.get(sec_key, {}).get("imagens")
        if imgs is not None:
            if not isinstance(imgs, list):
                return f"O campo 'imagens' na seção '{sec_key}' deve ser uma lista"
            for i, url in enumerate(imgs):
                if not isinstance(url, str) or not url.strip():
                    return f"A imagem {i+1} na seção '{sec_key}' deve ser uma URL válida (texto)"
    return None


def youtube_id(url):
    m = re.search(r"(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)([\w-]{11})", url)
    return m.group(1) if m else None


def guess_image_ext(raw):
    if raw.startswith(b"\x89PNG"):
        return ".png"
    if raw.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if raw.startswith(b"GIF87a") or raw.startswith(b"GIF89a"):
        return ".gif"
    if raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        return ".webp"
    return ".png"


class Handler(BaseHTTPRequestHandler):
    server_version = "QuintalServer/1.2"

    # ---------- helpers ----------
    def send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status, message):
        self.send_json({"erro": message}, status)

    def serve_file(self, path, content_type=None):
        if not os.path.isfile(path):
            self.send_error_json(404, "Não encontrado")
            return
        with open(path, "rb") as f:
            body = f.read()
        ct = content_type or (MIME_OVERRIDES.get(os.path.splitext(path)[1].lower())
                              or mimetypes.guess_type(path)[0]
                              or "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # log silencioso e limpo
        pass

    # ---------- roteamento ----------
    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        # Health check endpoint para o Render / Railway
        if path == "/healthz":
            return self.send_json({"status": "ok"})

        if path == "/api/atracoes":
            query = parsed.query
            params = urllib.parse.parse_qs(query)
            edicao_param = params.get("edicao", [None])[0]
            if not edicao_param:
                edicao_param = get_active_edicao_id()
            all_atracoes = load_data()
            filtered = [a for a in all_atracoes if a.get("edicao", "") == edicao_param]
            return self.send_json(filtered)

        if path == "/api/edicoes":
            return self.send_json(load_edicoes())

        if path == "/api/programacao":
            return self.send_json(load_programacao())

        if path == "/api/secoes":
            return self.send_json(load_secoes())

        if path == "/api/verify":
            if not is_authorized(self):
                return self.send_error_json(401, "Sessão expirada ou não autorizada")
            return self.send_json({"valido": True})

        if path in ("/", "/index.html"):
            return self.serve_file(os.path.join(ROOT, "quintal-sabores.html"))

        if path in ("/admin", "/admin.html"):
            return self.serve_file(os.path.join(ROOT, "admin.html"))

        # arquivos estáticos: /assets/... e /uploads/...
        if path.startswith("/assets/"):
            return self.serve_file(os.path.join(ROOT, "assets", path[len("/assets/"):]))
        if path.startswith("/uploads/"):
            return self.serve_file(os.path.join(ROOT, "uploads", path[len("/uploads/"):]))

        # trilha sonora do festival
        if path == "/trilha.mp3":
            return self.serve_file(os.path.join(ROOT, "trilha.mp3"))

        self.send_error_json(404, "Rota não encontrada")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path == "/api/login":
            ip = get_client_ip(self)
            now = time.time()
            attempts = [t for t in failed_logins.get(ip, []) if now - t < RATE_LIMIT_WINDOW]
            failed_logins[ip] = attempts

            if len(attempts) >= RATE_LIMIT_MAX:
                oldest = attempts[0]
                rem_sec = math.ceil((oldest + RATE_LIMIT_WINDOW) - now)
                rem_min = math.ceil(rem_sec / 60)
                return self.send_json({
                    "erro": f"Muitas tentativas de login. Tente novamente em {rem_min} minuto(s).",
                    "bloqueado_ate_segundos": max(1, rem_sec)
                }, 429)

            body = parse_json_body(self)
            if not body or body.get("senha") != ADMIN_PASSWORD:
                failed_logins[ip].append(now)
                return self.send_error_json(401, "Senha incorreta")

            failed_logins.pop(ip, None)
            token = secrets.token_hex(16)
            tokens[token] = now
            return self.send_json({"token": token})

        if path == "/api/atracoes":
            if not is_authorized(self):
                return self.send_error_json(401, "Não autorizado")
            body = parse_json_body(self)
            if not body or not isinstance(body, dict):
                return self.send_error_json(400, "Corpo inválido")
            err = validate_attraction(body)
            if err:
                return self.send_error_json(400, err)
            body["id"] = secrets.token_hex(8)
            if not body.get("edicao"):
                body["edicao"] = get_active_edicao_id()
            data = load_data()
            data.append(body)
            save_data(data)
            return self.send_json(body, 201)

        if path == "/api/edicoes":
            if not is_authorized(self):
                return self.send_error_json(401, "Não autorizado")
            body = parse_json_body(self)
            if not body or not isinstance(body, dict):
                return self.send_error_json(400, "Corpo inválido")
            if not body.get("nome") or not body.get("subtitulo"):
                return self.send_error_json(400, "Os campos (nome, subtitulo) são obrigatórios")
            
            body["id"] = f"ed_{secrets.token_hex(4)}"
            body["status"] = body.get("status", "arquivada")
            body.setdefault("ano", "")
            
            edicoes = load_edicoes()
            edicoes.append(body)
            save_edicoes(edicoes)
            return self.send_json(body, 201)

        if path == "/api/upload":
            if not is_authorized(self):
                return self.send_error_json(401, "Não autorizado")
            body = parse_json_body(self)
            if not body or not body.get("data"):
                return self.send_error_json(400, "Sem dados de imagem")
            try:
                raw = base64.b64decode(body["data"].split(",", 1)[-1])
            except Exception:
                return self.send_error_json(400, "Base64 inválido")
            if len(raw) > 20 * 1024 * 1024:
                return self.send_error_json(400, "Imagem muito grande (máx 20 MB)")
            ext = guess_image_ext(raw)
            # Mapeia extensão → content-type correto para o Storage
            ct_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}
            content_type = ct_map.get(ext, "image/jpeg")
            fname = secrets.token_hex(12) + ext

            # 1ª tentativa: Supabase Storage (fonte primária)
            storage_url = SupabaseClient.upload_to_storage("atracoes", fname, raw, content_type)
            if storage_url:
                return self.send_json({"url": storage_url, "storage": "supabase"})

            # Fallback: salva localmente se o Supabase estiver indisponível
            with open(os.path.join(UPLOAD_DIR, fname), "wb") as f:
                f.write(raw)
            return self.send_json({"url": "/uploads/" + fname, "storage": "local"})

        self.send_error_json(404, "Rota não encontrada")

    def do_PUT(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path == "/api/programacao":
            if not is_authorized(self):
                return self.send_error_json(401, "Não autorizado")
            body = parse_json_body(self)
            if body is None:
                return self.send_error_json(400, "Corpo JSON inválido")
            err = validate_programacao(body)
            if err:
                return self.send_error_json(400, err)
            save_programacao(body)
            return self.send_json(body)

        if path == "/api/secoes":
            if not is_authorized(self):
                return self.send_error_json(401, "Não autorizado")
            body = parse_json_body(self)
            if body is None:
                return self.send_error_json(400, "Corpo JSON inválido")
            err = validate_secoes(body)
            if err:
                return self.send_error_json(400, err)
            save_secoes(body)
            return self.send_json(body)

        if path == "/api/edicoes":
            if not is_authorized(self):
                return self.send_error_json(401, "Não autorizado")
            body = parse_json_body(self)
            if body is None or not isinstance(body, list):
                return self.send_error_json(400, "Corpo JSON inválido, deve ser uma lista")
                
            save_edicoes(body)
            return self.send_json(body)

        if path == "/api/edicoes/encerrar":
            if not is_authorized(self):
                return self.send_error_json(401, "Não autorizado")
            edicoes = load_edicoes()
            for ed in edicoes:
                ed["status"] = "arquivada"
            save_edicoes(edicoes)
            return self.send_json({"sucesso": True, "edicoes": edicoes})

        if path == "/api/edicoes/arquivar":
            if not is_authorized(self):
                return self.send_error_json(401, "Não autorizado")
            body = parse_json_body(self)
            if not body or not isinstance(body, dict):
                return self.send_error_json(400, "Corpo inválido")
            
            edicoes = load_edicoes()
            target_id = body.get("id")
            found = False
            if target_id:
                for ed in edicoes:
                    if ed["id"] == target_id:
                        ed["status"] = "ativa"
                        found = True
                    else:
                        ed["status"] = "arquivada"
            
            if not found:
                if not body.get("nome") or not body.get("subtitulo"):
                    return self.send_error_json(400, "Dados da nova edição são obrigatórios (nome, subtitulo)")
                for ed in edicoes:
                    ed["status"] = "arquivada"
                new_id = target_id or f"ed_{secrets.token_hex(4)}"
                new_edition = {
                    "id": new_id,
                    "ano": body.get("ano", ""),
                    "nome": body["nome"],
                    "subtitulo": body["subtitulo"],
                    "status": "ativa"
                }
                edicoes.append(new_edition)
                
            save_edicoes(edicoes)
            return self.send_json({"sucesso": True, "edicoes": edicoes})

        m = re.match(r"^/api/atracoes/([\w-]+)$", path)
        if not m:
            return self.send_error_json(404, "Rota não encontrada")
        if not is_authorized(self):
            return self.send_error_json(401, "Não autorizado")
        body = parse_json_body(self)
        if not body or not isinstance(body, dict):
            return self.send_error_json(400, "Corpo inválido")
        err = validate_attraction(body)
        if err:
            return self.send_error_json(400, err)
        aid = m.group(1)
        body["id"] = aid
        
        data = load_data()
        idx, existing = find_attraction(data, aid)
        # Preserva a edição anterior se não foi enviada
        if not body.get("edicao"):
            body["edicao"] = existing.get("edicao") if existing else get_active_edicao_id()
            
        if idx is not None:
            data[idx] = body
        else:
            data.append(body)
        save_data(data)
        return self.send_json(body)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        m = re.match(r"^/api/atracoes/([\w-]+)$", path)
        if not m:
            return self.send_error_json(404, "Rota não encontrada")
        if not is_authorized(self):
            return self.send_error_json(401, "Não autorizado")
        aid = m.group(1)
        data = load_data()
        idx, _ = find_attraction(data, aid)
        if idx is None:
            return self.send_error_json(404, "Atração não encontrada")
        removed = data.pop(idx)
        save_data(data)
        SupabaseClient.delete_eq("atracoes", "id", aid)
        return self.send_json({"ok": True, "removida": removed})


if __name__ == "__main__":
    import threading

    if not os.path.exists(DATA_FILE):
        save_json_file(DATA_FILE, [])
    if not os.path.exists(PROGRAMACAO_FILE):
        save_json_file(PROGRAMACAO_FILE, [])
    if not os.path.exists(SECOES_FILE):
        save_json_file(SECOES_FILE, {})
    if not os.path.exists(EDICOES_FILE):
        # Cria arquivo inicial com as edições padrão do festival
        default_eds = [
            {"id": "ed_2026_6", "ano": "2026", "nome": "6ª Edição", "subtitulo": "13 e 14 de junho · Bairro Boa Vista", "status": "ativa"},
            {"id": "ed_2025_5", "ano": "2025", "nome": "5ª Edição", "subtitulo": "Junho 2025 · Ver galeria", "status": "arquivada"},
            {"id": "ed_2024_4", "ano": "2024", "nome": "4ª Edição", "subtitulo": "Junho 2024 · Ver galeria", "status": "arquivada"},
            {"id": "ed_2023_3", "ano": "2023", "nome": "3ª Edição", "subtitulo": "Junho 2023 · Ver galeria", "status": "arquivada"}
        ]
        save_json_file(EDICOES_FILE, default_eds)

    # Seed e migrações rodam em background para não travar o boot
    # (evita timeout no health check do Render / Railway)
    def _background_init():
        try:
            seed_database_if_needed()
        except Exception as e:
            print(f"[Background Init] Erro no seed: {e}")
        try:
            migrate_images_to_supabase_storage()
        except Exception as e:
            print(f"[Background Init] Erro na migração de imagens: {e}")

    bg = threading.Thread(target=_background_init, daemon=True)
    bg.start()

    print(f"Servidor rodando em http://0.0.0.0:{PORT}")
    print(f"  Site:  http://localhost:{PORT}/")
    print(f"  Admin: http://localhost:{PORT}/admin")
    httpd = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
