# CRAS — Sistema de Atendimento (Streamlit)

App que substitui a planilha `Base_de_Dados_v4.xlsm` original: mesmo fluxo de
lançamento diário, geração de mapa de atendimento em PDF e um dashboard —
mas rodando como aplicação web em Python, sem os limites de linhas/células
do Excel ou do Google Sheets, e sem depender de macros.

## O que tem aqui
- **`app.py`** — o app (4 páginas: Lançamento Diário, Mapa de Atendimento, Dashboard, Base de Dados).
- **`db.py`** — camada de dados. Usa **PostgreSQL** (Supabase ou qualquer Postgres) como banco — os dados ficam fora do disco do Streamlit Cloud, então sobrevivem a reinicializações, sono do app e deploys novos.
- **`pdf_mapa.py`** — gera o PDF do mapa de atendimento diário (equivalente à macro `GerarMapaPDF`).
- **`data/medicos.json`** — lista de profissionais (36 no total: 31 da aba "Informações" + 5 que só apareciam no histórico, veja abaixo).
- **`data/base_historico.json`** — **os 1.970 registros reais** da aba "Base 2025 - 2026" (jan/2025 a jul/2026), com todos os totais por dia/médico. É carregado automaticamente no banco na primeira vez que o app roda contra um banco vazio.
- **`.streamlit/config.toml`** — tema visual (cores extraídas do brasão do CRAS).
- **`.streamlit/secrets.toml.example`** — modelo de como configurar a conexão com o banco (veja abaixo).
- **`requirements.txt`** — dependências Python.

### Sobre a base histórica
Na primeira versão que te entreguei eu só tinha trazido a lista de médicos —
**não tinha percebido que a aba "Base 2025 - 2026" continha 1.970 linhas de
dados reais** (a aba "Ficha", essa sim, estava genuinamente vazia no arquivo
original). Corrigido: agora o histórico completo é importado automaticamente
para o banco na primeira execução (contra um banco vazio), e o Dashboard já
usa esses números reais. Confirmei a soma: **6.799 atendimentos** no total
histórico importado.

Um detalhe de qualidade dos dados que encontrei ao importar: a aba "Base 2025
- 2026" usava nomes de médicos escritos de forma diferente da aba
"Informações" (com/sem acento, maiúsculas/minúsculas — ex: "João Dehon..."
vs "JOAO DEHON..."). Fiz o casamento ignorando acentuação e caixa para não
duplicar médicos por engano; 9 nomes bateram dessa forma, e 5 nomes do
histórico realmente não existiam na aba "Informações" (provavelmente
profissionais que já saíram do quadro) — esses entraram como registros novos
na lista de médicos, sem uma "Meta" definida.

## Configurar o banco de dados (obrigatório antes de rodar)
O app precisa de um Postgres — recomendo o [Supabase](https://supabase.com)
(gratuito). Depois de criar o projeto lá:

1. No painel do Supabase, clique em **Connect** (topo da página) > aba **URI**.
2. Copie a connection string e troque `[YOUR-PASSWORD]` pela senha do banco
   que você definiu ao criar o projeto.
3. Configure essa string em um dos dois lugares:
   - **Rodando localmente:** copie `.streamlit/secrets.toml.example` para
     `.streamlit/secrets.toml` e cole a string lá.
   - **No Streamlit Community Cloud:** vá em Settings do app > Secrets, e
     cole:
     ```toml
     supabase_db_url = "postgresql://...sua string completa..."
     ```
4. **Nunca** suba o `secrets.toml` de verdade para o GitHub (ele tem a senha
   do banco) — só o `.example` deve ir para o repositório.

Na primeira vez que o app conectar num banco vazio, ele cria as tabelas e
importa o histórico automaticamente — não precisa rodar nenhum script à parte.

## Como rodar localmente
```bash
# 1. Crie um ambiente virtual (recomendado)
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 2. Instale as dependências
pip install -r requirements.txt

# 3. Configure o banco (veja seção acima) antes do primeiro run

# 4. Rode o app
streamlit run app.py
```
Ele abre sozinho no navegador (geralmente em `http://localhost:8501`).

## Como publicar de graça (para acessar de qualquer lugar, sem instalar nada)
1. Crie um repositório no GitHub e suba esta pasta inteira (**exceto**
   `.streamlit/secrets.toml`, se você criou um local — só o `.example` deve
   ir para o repositório).
2. Acesse [share.streamlit.io](https://share.streamlit.io), conecte sua conta
   do GitHub e escolha o repositório.
3. Aponte o "Main file path" para `app.py`.
4. Antes de publicar (ou logo depois, em Settings > Secrets), cole a
   connection string do Supabase — veja a seção "Configurar o banco de
   dados" acima.
5. Pronto — você recebe uma URL pública (grátis, no plano Community) para
   acessar o sistema de qualquer navegador, e agora os dados **não somem**
   quando o app dorme ou reinicia, porque ficam no Postgres, fora do
   container do Streamlit.

## Diferenças em relação ao arquivo original
- **Assistido/Servidor**: no lugar de duas caixinhas que se anulavam (com um
  bug no arquivo original — veja a conversa anterior), aqui é um único campo
  de seleção com 3 opções (Discente / Discente assistido / Servidor), o que é
  mais claro e evita o tipo de inconsistência que existia na planilha.
- **Um nome de médico duplicado**: a planilha original tinha "WALERIA PEREIRA
  VIANA" cadastrada duas vezes (códigos C2 e E2, mesma especialidade). Como o
  app usa o nome como identificador único no formulário, mantive só o primeiro
  registro. Se as duas entradas eram intencionais (ex: dois turnos/contratos
  diferentes), me avise que ajusto para diferenciá-las (ex: por código).

## Login e perfis de acesso
O app tem dois perfis, cada um com sua própria senha:
- **Recepção**: acesso a Lançamento Diário e Mapa de Atendimento.
- **Administrador**: acesso total (também Dashboard e Base de Dados).

Na primeira vez que alguém abrir o app, ele pede para definir as duas senhas
antes de liberar qualquer página. Depois disso, é só escolher o perfil e
digitar a senha na tela de login.

Para trocar qualquer uma das duas senhas depois, entre como Administrador e
vá em **Base de Dados > ⚙️ Configurações**.

⚠️ Assim como a senha do Chefe de Setor e demais configurações, essas senhas
ficam salvas sem criptografia no banco (tabela `config`) — é uma proteção
simples contra acesso casual, não um controle de acesso robusto. Se for
publicar o app na internet para várias pessoas acessarem, vale considerar algo
mais forte (ex: `st.secrets` + um provedor de autenticação de verdade).

## Testado
- App sobe e responde (HTTP 200) sem erros, rodando contra um Postgres real.
- Fluxo completo testado de ponta a ponta: cadastro de atendimento → gravação
  no banco → agregação por dia/médico → geração do PDF do mapa → dashboard.
- Login testado nos dois perfis (Recepção e Administrador), incluindo senha
  errada, troca de senha, e restrição de páginas por perfil.
- Backup e restauração testados simulando perda total do banco.
- Concorrência testada com 8 "usuários" simulados salvando ao mesmo tempo
  (encontrei e corrigi uma condição de corrida real nesse teste — veja
  histórico da conversa).
