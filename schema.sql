-- Festival Quintal dos Sabores — Schema PostgreSQL para Supabase
-- Execute este script no SQL Editor do Supabase (https://supabase.com/dashboard/project/wowzbcvqfsibkfyjpnbp/sql)

-- 1. Tabela de Atrações (Atualizada com a coluna de edição)
CREATE TABLE IF NOT EXISTS public.atracoes (
  id TEXT PRIMARY KEY,
  nome TEXT NOT NULL,
  tag TEXT,
  tipo TEXT,
  destaque BOOLEAN DEFAULT FALSE,
  media JSONB NOT NULL,
  edicao TEXT DEFAULT '',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Garantir que a coluna edicao existe se a tabela já foi criada anteriormente
ALTER TABLE public.atracoes ADD COLUMN IF NOT EXISTS edicao TEXT DEFAULT '';
-- Migração: remover o DEFAULT antigo '2026' para novos registros
ALTER TABLE public.atracoes ALTER COLUMN edicao SET DEFAULT '';

-- 2. Tabela de Programação
CREATE TABLE IF NOT EXISTS public.programacao (
  id TEXT PRIMARY KEY,
  dia_num TEXT NOT NULL,
  dia_nome TEXT NOT NULL,
  mes_ano TEXT NOT NULL,
  itens JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Tabela de Seções
CREATE TABLE IF NOT EXISTS public.secoes (
  id TEXT PRIMARY KEY DEFAULT 'main',
  dados JSONB NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Tabela de Edições (Atualizada — campo 'nome' substituiu 'numero_edicao')
CREATE TABLE IF NOT EXISTS public.edicoes (
  id TEXT PRIMARY KEY,
  ano TEXT NOT NULL DEFAULT '',
  nome TEXT NOT NULL DEFAULT '',
  subtitulo TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL CHECK (status IN ('ativa', 'arquivada')),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Migração: se a tabela já existir com 'numero_edicao', adicionar 'nome' e copiar dados
ALTER TABLE public.edicoes ADD COLUMN IF NOT EXISTS nome TEXT NOT NULL DEFAULT '';
UPDATE public.edicoes SET nome = numero_edicao WHERE nome = '' AND numero_edicao IS NOT NULL AND numero_edicao != '';
-- (coluna numero_edicao antiga pode ser removida depois se desejado)

-- Habilitar RLS (Row Level Security) em todas as tabelas
ALTER TABLE public.atracoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.programacao ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.secoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.edicoes ENABLE ROW LEVEL SECURITY;

-- Limpeza de políticas antigas
DROP POLICY IF EXISTS "Leitura pública atracoes" ON public.atracoes;
DROP POLICY IF EXISTS "Escrita apenas service_role atracoes" ON public.atracoes;
DROP POLICY IF EXISTS "Leitura pública programacao" ON public.programacao;
DROP POLICY IF EXISTS "Escrita apenas service_role programacao" ON public.programacao;
DROP POLICY IF EXISTS "Leitura pública secoes" ON public.secoes;
DROP POLICY IF EXISTS "Escrita apenas service_role secoes" ON public.secoes;
DROP POLICY IF EXISTS "Leitura pública edicoes" ON public.edicoes;
DROP POLICY IF EXISTS "Escrita apenas service_role edicoes" ON public.edicoes;

-- 1. Políticas para Atrações (Leitura pública anon, Escrita estrita service_role)
CREATE POLICY "Leitura pública atracoes" ON public.atracoes
  FOR SELECT TO anon, authenticated, service_role
  USING (true);

CREATE POLICY "Escrita apenas service_role atracoes" ON public.atracoes
  FOR ALL TO service_role
  USING (true) WITH CHECK (true);

-- 2. Políticas para Programação (Leitura pública anon, Escrita estrita service_role)
CREATE POLICY "Leitura pública programacao" ON public.programacao
  FOR SELECT TO anon, authenticated, service_role
  USING (true);

CREATE POLICY "Escrita apenas service_role programacao" ON public.programacao
  FOR ALL TO service_role
  USING (true) WITH CHECK (true);

-- 3. Políticas para Seções (Leitura pública anon, Escrita estrita service_role)
CREATE POLICY "Leitura pública secoes" ON public.secoes
  FOR SELECT TO anon, authenticated, service_role
  USING (true);

CREATE POLICY "Escrita apenas service_role secoes" ON public.secoes
  FOR ALL TO service_role
  USING (true) WITH CHECK (true);

-- 4. Políticas para Edições (Leitura pública anon, Escrita estrita service_role)
CREATE POLICY "Leitura pública edicoes" ON public.edicoes
  FOR SELECT TO anon, authenticated, service_role
  USING (true);

CREATE POLICY "Escrita apenas service_role edicoes" ON public.edicoes
  FOR ALL TO service_role
  USING (true) WITH CHECK (true);
