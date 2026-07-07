from flask import Flask, render_template, request, redirect, url_for, session, send_file
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.pdfgen import canvas
import sqlite3
import os
import datetime
import io

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'chave-secreta-padrao-troque-em-producao')

PASTA_ATUAL = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(PASTA_ATUAL, 'atividades.db')
STATIC_DIR = os.path.join(PASTA_ATUAL, 'static')
EXTENSOES_IMAGEM = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


# ─────────────────────────────────────────────
#  BANCO DE DADOS
# ─────────────────────────────────────────────

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()

    conn.execute('''
                CREATE TABLE IF NOT EXISTS atividades (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            area        TEXT    NOT NULL,
            atividade   TEXT    NOT NULL,
            responsavel TEXT    NOT NULL,
            status      TEXT    NOT NULL,
            prazo       TEXT,
            arquivado   INTEGER DEFAULT 0,
            prioridade  TEXT    DEFAULT 'Baixa'
        )
    ''')

    conn.execute('''
        CREATE TABLE IF NOT EXISTS passos (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            atividade_id INTEGER NOT NULL,
            descricao    TEXT    NOT NULL,
            prazo        TEXT,
            concluido    INTEGER DEFAULT 0,
            FOREIGN KEY(atividade_id) REFERENCES atividades(id)
        )
    ''')

    # Migrações seguras — ignoram erro se coluna já existe
    

    conn.execute('''
        CREATE TABLE IF NOT EXISTS categorias (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT    NOT NULL UNIQUE,
            cor  TEXT    NOT NULL
        )
    ''')

    conn.execute('''
        CREATE TABLE IF NOT EXISTS responsaveis (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            nome  TEXT    NOT NULL UNIQUE,
            email TEXT,
            cargo TEXT,
            idade INTEGER,
            foto  TEXT
        )
    ''')

    # Migrações de colunas que podem já existir
    for sql in [
        'ALTER TABLE atividades ADD COLUMN data_inicio TEXT',
        'ALTER TABLE atividades ADD COLUMN observacoes TEXT',
        'ALTER TABLE responsaveis ADD COLUMN email TEXT',
        'ALTER TABLE responsaveis ADD COLUMN cargo TEXT',
        'ALTER TABLE responsaveis ADD COLUMN idade INTEGER',
        'ALTER TABLE responsaveis ADD COLUMN foto  TEXT',
    ]:
        _safe_alter(conn, sql)

    conn.execute('''
        CREATE TABLE IF NOT EXISTS credenciais (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            servico     TEXT NOT NULL,
            usuario     TEXT NOT NULL,
            senha_hash  TEXT NOT NULL,
            observacoes TEXT
        )
    ''')

    conn.execute('''
        CREATE TABLE IF NOT EXISTS procedimentos (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo           TEXT NOT NULL,
            categoria        TEXT,
            conteudo         TEXT,
            data_atualizacao TEXT
        )
    ''')

    # Adiciona a coluna 'categoria' se ela não existir (migração)
    _safe_alter(conn, 'ALTER TABLE procedimentos ADD COLUMN categoria TEXT')

    # Renomeia coluna legada 'senha' → 'senha_hash' de forma compatível com SQLite antigo
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(credenciais)").fetchall()]
        if 'senha' in cols and 'senha_hash' not in cols:
            conn.execute('ALTER TABLE credenciais RENAME COLUMN senha TO senha_hash')
    except Exception:
        pass

    conn.execute('''
        CREATE TABLE IF NOT EXISTS configuracao_seguranca (
            chave TEXT PRIMARY KEY,
            valor TEXT NOT NULL
        )
    ''')

    cursor = conn.cursor()

    # Senha mestre padrão
    cursor.execute('SELECT COUNT(*) FROM configuracao_seguranca WHERE chave = "senha_mestre"')
    if cursor.fetchone()[0] == 0:
        conn.execute(
            'INSERT INTO configuracao_seguranca (chave, valor) VALUES ("senha_mestre", ?)',
            (generate_password_hash('271828Jv.'),)
        )

    # Categorias iniciais
    cursor.execute('SELECT COUNT(*) FROM categorias')
    if cursor.fetchone()[0] == 0:
        conn.executemany('INSERT INTO categorias (nome, cor) VALUES (?, ?)', [
            ("LidIA",                    "#3b82f6"),
            ("Germina",                  "#eab308"),
            ("Sistema de Gestão/Coda",   "#06b6d4"),
            ("Imersões",                 "#ec4899"),
            ("Acompanhamento",           "#22c55e"),
            ("Outros",                   "#64748b"),
        ])

    # Responsáveis iniciais
    cursor.execute('SELECT COUNT(*) FROM responsaveis')
    if cursor.fetchone()[0] == 0:
        conn.executemany('INSERT INTO responsaveis (nome) VALUES (?)',
                         [("João",), ("Edu",), ("Elvis",), ("Felipe",)])

    # Dados padrão do João
    conn.execute('''
        UPDATE responsaveis
        SET email = "joao.victor@ufc.br",
            cargo = "Estudante de Ciências Econômicas / Analista de Dados",
            idade = 22
        WHERE nome = "João" AND email IS NULL
    ''')

    conn.commit()
    conn.close()


def _safe_alter(conn, sql):
    """Executa um ALTER TABLE ignorando erro de coluna duplicada."""
    try:
        conn.execute(sql)
    except sqlite3.OperationalError:
        pass


def _redirect_back(default_endpoint='index'):
    destino = request.form.get('next') or request.referrer
    if destino and destino.startswith('/'):
        return redirect(destino)
    return redirect(url_for(default_endpoint))


# ─────────────────────────────────────────────
#  CONTEXTO GLOBAL (sem duplicata)
# ─────────────────────────────────────────────

@app.context_processor
def inject_globals():
    return dict(font_size=session.get('font_size', 14))


# ─────────────────────────────────────────────
#  ROTAS PRINCIPAIS
# ─────────────────────────────────────────────

def processar_atividades(atividades_rows):
    import datetime
    resultado = []
    hoje = datetime.date.today().strftime('%Y-%m-%d')
    for a in atividades_rows:
        d = dict(a)
        if d['status'] != 'Feito' and d.get('prazo') and d['prazo'] < hoje:
            d['status_exibicao'] = 'Atrasado'
        else:
            d['status_exibicao'] = d['status']
        resultado.append(d)
    return resultado

def calcular_metricas(atv_ativas, atv_arq):
    m = {
        'Pendente':      sum(1 for a in atv_ativas if a['status_exibicao'] == 'Pendente'),
        'Em andamento':  sum(1 for a in atv_ativas if a['status_exibicao'] == 'Em andamento'),
        'Atrasado':      sum(1 for a in atv_ativas if a['status_exibicao'] == 'Atrasado'),
        'Feito':         sum(1 for a in atv_ativas if a['status_exibicao'] == 'Feito'),
        'Total':         len(atv_ativas),
        'Pendente_Arq':  sum(1 for a in atv_arq if a['status_exibicao'] == 'Pendente'),
        'Em andamento_Arq': sum(1 for a in atv_arq if a['status_exibicao'] == 'Em andamento'),
        'Atrasado_Arq':  sum(1 for a in atv_arq if a['status_exibicao'] == 'Atrasado'),
        'Feito_Arq':     sum(1 for a in atv_arq if a['status_exibicao'] == 'Feito'),
        'Total_Arq':     len(atv_arq)
    }
    m['Total_Geral'] = m['Total'] + m['Total_Arq']
    return m

@app.route('/')
def index():
    conn = get_db_connection()
    atividades_raw  = conn.execute('SELECT * FROM atividades WHERE arquivado = 0 ORDER BY id DESC').fetchall()
    atividades_arq_raw = conn.execute('SELECT * FROM atividades WHERE arquivado = 1 ORDER BY id DESC').fetchall()
    categorias  = conn.execute('SELECT * FROM categorias').fetchall()
    responsaveis = conn.execute('SELECT * FROM responsaveis ORDER BY nome ASC').fetchall()
    
    atividades = processar_atividades(atividades_raw)
    atividades_arq = processar_atividades(atividades_arq_raw)
    metricas = calcular_metricas(atividades, atividades_arq)
    
    conn.close()
    return render_template('index.html',
                           atividades=atividades,
                           atividades_arq=atividades_arq,
                           categorias=categorias,
                           responsaveis=responsaveis,
                           metricas=metricas,
                           modo="ativos")


@app.route('/arquivados')
def arquivados():
    conn = get_db_connection()
    atividades_raw  = conn.execute('SELECT * FROM atividades WHERE arquivado = 1 ORDER BY id DESC').fetchall()
    categorias  = conn.execute('SELECT * FROM categorias').fetchall()
    responsaveis = conn.execute('SELECT * FROM responsaveis ORDER BY nome ASC').fetchall()
    
    atividades = processar_atividades(atividades_raw)
    conn.close()
    return render_template('index.html',
                           atividades=atividades,
                           categorias=categorias,
                           responsaveis=responsaveis,
                           modo="arquivados")


@app.route('/configuracoes')
def configuracoes():
    conn = get_db_connection()
    categorias  = conn.execute('SELECT * FROM categorias').fetchall()
    responsaveis = conn.execute('SELECT * FROM responsaveis ORDER BY nome ASC').fetchall()
    conn.close()
    return render_template('index.html',
                           categorias=categorias,
                           responsaveis=responsaveis,
                           modo="configuracoes")


# ─────────────────────────────────────────────
#  USUÁRIOS
# ─────────────────────────────────────────────

@app.route('/usuarios')
def usuarios():
    conn = get_db_connection()
    responsaveis = conn.execute('SELECT * FROM responsaveis ORDER BY nome ASC').fetchall()
    conn.close()
    return render_template('index.html', responsaveis=responsaveis, modo="usuarios")


@app.route('/usuarios/<int:id>')
def usuario_detalhe(id):
    conn = get_db_connection()
    usuario = conn.execute('SELECT * FROM responsaveis WHERE id = ?', (id,)).fetchone()
    if not usuario:
        conn.close()
        return redirect(url_for('usuarios'))

    atividades_raw = conn.execute(
        'SELECT * FROM atividades WHERE responsavel = ? AND arquivado = 0 ORDER BY id DESC',
        (usuario['nome'],)
    ).fetchall()
    atividades_arq_raw = conn.execute(
        'SELECT * FROM atividades WHERE responsavel = ? AND arquivado = 1 ORDER BY id DESC',
        (usuario['nome'],)
    ).fetchall()
    categorias    = conn.execute('SELECT * FROM categorias').fetchall()
    responsaveis  = conn.execute('SELECT * FROM responsaveis ORDER BY nome ASC').fetchall()
    
    atividades = processar_atividades(atividades_raw)
    atividades_arq = processar_atividades(atividades_arq_raw)
    metricas = calcular_metricas(atividades, atividades_arq)
    conn.close()

    return render_template('index.html',
                           usuario=usuario,
                           atividades=atividades,
                           categorias=categorias,
                           responsaveis=responsaveis,
                           metricas=metricas,
                           modo="usuario_detalhe")


@app.route('/usuarios/editar_cadastro/<int:id>', methods=['POST'])
def editar_cadastro(id):
    cargo = request.form.get('cargo', '')
    email = request.form.get('email', '')

    conn = get_db_connection()

    file = request.files.get('foto')
    if file and file.filename:
        extensao = secure_filename(file.filename).rsplit('.', 1)[-1].lower()
        if extensao in EXTENSOES_IMAGEM:
            os.makedirs(STATIC_DIR, exist_ok=True)
            nome_arquivo = f"foto_user_{id}.{extensao}"
            file.save(os.path.join(STATIC_DIR, nome_arquivo))
            conn.execute('UPDATE responsaveis SET foto = ? WHERE id = ?', (nome_arquivo, id))

    conn.execute('UPDATE responsaveis SET cargo = ?, email = ? WHERE id = ?', (cargo, email, id))
    conn.commit()
    conn.close()
    return redirect(url_for('usuario_detalhe', id=id))


# ─────────────────────────────────────────────
#  CREDENCIAIS (COFRE)
# ─────────────────────────────────────────────

@app.route('/credenciais', methods=['GET', 'POST'])
def credenciais():
    erro = None
    conn = get_db_connection()

    if request.method == 'POST' and request.form.get('acao') == 'login':
        senha_digitada = request.form.get('senha_mestre', '')
        db_hash = conn.execute(
            'SELECT valor FROM configuracao_seguranca WHERE chave = "senha_mestre"'
        ).fetchone()
        if db_hash and check_password_hash(db_hash['valor'], senha_digitada):
            session['cofre_autenticado'] = True
            conn.close()
            return redirect(url_for('credenciais'))
        erro = "Senha Mestre incorreta!"

    if session.get('cofre_autenticado'):
        contas = conn.execute('SELECT * FROM credenciais ORDER BY servico ASC').fetchall()
        conn.close()
        return render_template('index.html', contas=contas, modo="credenciais")

    conn.close()
    return render_template('index.html', modo="credenciais_login", erro=erro)


@app.route('/credenciais/adicionar', methods=['POST'])
def credenciais_adicionar():
    if not session.get('cofre_autenticado'):
        return redirect(url_for('credenciais'))

    conn = get_db_connection()
    conn.execute(
        'INSERT INTO credenciais (servico, usuario, senha_hash, observacoes) VALUES (?, ?, ?, ?)',
        (
            request.form['servico'],
            request.form['usuario'],
            generate_password_hash(request.form['senha']),   # ← armazena hash, não texto puro
            request.form.get('observacoes', ''),
        )
    )
    conn.commit()
    conn.close()
    return redirect(url_for('credenciais'))


@app.route('/credenciais/deletar/<int:id>', methods=['POST'])
def credenciais_deletar(id):
    if not session.get('cofre_autenticado'):
        return redirect(url_for('credenciais'))
    conn = get_db_connection()
    conn.execute('DELETE FROM credenciais WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('credenciais'))


@app.route('/credenciais/sair')
def credenciais_sair():
    session.pop('cofre_autenticado', None)
    return redirect(url_for('index'))


# ─────────────────────────────────────────────
#  PROCEDIMENTOS
# ─────────────────────────────────────────────

@app.route('/procedimentos')
def procedimentos():
    conn = get_db_connection()
    procedimentos = conn.execute('SELECT * FROM procedimentos ORDER BY titulo ASC').fetchall()
    categorias = conn.execute('SELECT * FROM categorias').fetchall()
    conn.close()
    return render_template('index.html', procedimentos=procedimentos, categorias=categorias, modo="procedimentos")


@app.route('/procedimentos/adicionar', methods=['POST'])
def procedimentos_adicionar():
    titulo = request.form.get('titulo', 'Sem título')
    categoria = request.form.get('categoria', 'Outros')
    conteudo = request.form.get('conteudo', '')
    data = datetime.datetime.now().strftime('%d/%m/%Y %H:%M')

    conn = get_db_connection()
    conn.execute(
        'INSERT INTO procedimentos (titulo, categoria, conteudo, data_atualizacao) VALUES (?, ?, ?, ?)',
        (titulo, categoria, conteudo, data)
    )
    conn.commit()
    conn.close()
    return redirect(url_for('procedimentos'))


@app.route('/procedimentos/editar/<int:id>', methods=['POST'])
def procedimentos_editar(id):
    titulo = request.form.get('titulo', 'Sem título')
    categoria = request.form.get('categoria', 'Outros')
    conteudo = request.form.get('conteudo', '')
    data = datetime.datetime.now().strftime('%d/%m/%Y %H:%M')

    conn = get_db_connection()
    conn.execute(
        'UPDATE procedimentos SET titulo = ?, categoria = ?, conteudo = ?, data_atualizacao = ? WHERE id = ?',
        (titulo, categoria, conteudo, data, id)
    )
    conn.commit()
    conn.close()
    return redirect(url_for('procedimentos'))


@app.route('/procedimentos/deletar/<int:id>', methods=['POST'])
def procedimentos_deletar(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM procedimentos WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('procedimentos'))



# ─────────────────────────────────────────────
#  API (AJAX) - AUTO-SAVE E PASSOS
# ─────────────────────────────────────────────
@app.route('/api/atividades/<int:id>/atualizar', methods=['POST'])
def api_atualizar_atividade(id):
    conn = get_db_connection()
    campo = request.form.get('campo')
    valor = request.form.get('valor')
    
    campos_permitidos = ['area', 'atividade', 'responsavel', 'status', 'prazo', 'prioridade', 'data_inicio']
    if campo in campos_permitidos:
        conn.execute(f'UPDATE atividades SET {campo} = ? WHERE id = ?', (valor, id))
        conn.commit()
    conn.close()
    return jsonify({"status": "success"})

@app.route('/api/atividades/<int:id>/painel_geral', methods=['GET'])
def painel_geral(id):
    conn = get_db_connection()
    atv = conn.execute('SELECT * FROM atividades WHERE id = ?', (id,)).fetchone()
    if not atv:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
        
    passos = conn.execute('SELECT * FROM passos WHERE atividade_id = ?', (id,)).fetchall()
    conn.close()
    
    total_passos = len(passos)
    concluidos = sum(1 for p in passos if p['concluido'])
    perc = int((concluidos / total_passos * 100)) if total_passos > 0 else 0
    
    # Calculate Atrasado status
    import datetime
    hoje = datetime.date.today().strftime('%Y-%m-%d')
    d = dict(atv)
    if d['status'] != 'Feito' and d.get('prazo') and d['prazo'] < hoje:
        status_exibicao = 'Atrasado'
    else:
        status_exibicao = d['status']

    return jsonify({
        'id': atv['id'],
        'atividade': atv['atividade'],
        'area': atv['area'],
        'responsavel': atv['responsavel'],
        'prioridade': atv['prioridade'],
        'data_inicio': atv['data_inicio'] or '',
        'prazo': atv['prazo'] or '',
        'observacoes': atv['observacoes'] or '',
        'perc_execucao': perc,
        'status': atv['status'],
        'status_exibicao': status_exibicao
    })

@app.route('/api/atividades/<int:id>/observacoes', methods=['POST'])
def salvar_observacoes(id):
    obs = request.form.get('observacoes', '')
    conn = get_db_connection()
    conn.execute('UPDATE atividades SET observacoes = ? WHERE id = ?', (obs, id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/atividades/<int:id>/passos', methods=['GET'])
def api_get_passos(id):
    conn = get_db_connection()
    passos = conn.execute('SELECT * FROM passos WHERE atividade_id = ? ORDER BY id ASC', (id,)).fetchall()
    conn.close()
    return jsonify([dict(p) for p in passos])

@app.route('/api/passos/<int:id>/toggle', methods=['POST'])
def api_toggle_passo(id):
    concluido = 1 if request.form.get('concluido') == 'true' else 0
    conn = get_db_connection()
    
    # Get atividade_id
    passo = conn.execute('SELECT atividade_id FROM passos WHERE id = ?', (id,)).fetchone()
    if not passo:
        return jsonify({"status": "error"}), 404
        
    atividade_id = passo['atividade_id']
    
    # Update passo
    conn.execute('UPDATE passos SET concluido = ? WHERE id = ?', (concluido, id))
    
    # Check if all steps are done
    todos_passos = conn.execute('SELECT concluido FROM passos WHERE atividade_id = ?', (atividade_id,)).fetchall()
    todos_concluidos = all(p['concluido'] == 1 for p in todos_passos) if todos_passos else False
    algum_concluido = any(p['concluido'] == 1 for p in todos_passos) if todos_passos else False
    
    novo_status = None
    if todos_concluidos and todos_passos:
        conn.execute('UPDATE atividades SET status = "Feito" WHERE id = ?', (atividade_id,))
        novo_status = "Feito"
    elif algum_concluido:
        conn.execute('UPDATE atividades SET status = "Em andamento" WHERE id = ?', (atividade_id,))
        novo_status = "Em andamento"
    elif not algum_concluido and todos_passos:
        conn.execute('UPDATE atividades SET status = "Pendente" WHERE id = ?', (atividade_id,))
        novo_status = "Pendente"
        
    conn.commit()
    conn.close()
    
    return jsonify({"status": "success", "todos_concluidos": todos_concluidos, "novo_status_atividade": novo_status})

@app.route('/api/passos/adicionar', methods=['POST'])
def api_adicionar_passo():
    atividade_id = request.form.get('atividade_id')
    descricao = request.form.get('descricao')
    prazo = request.form.get('prazo')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO passos (atividade_id, descricao, prazo, concluido) VALUES (?, ?, ?, 0)',
                 (atividade_id, descricao, prazo if prazo else None))
    novo_id = cursor.lastrowid
    
    # Se adicionar um passo novo (incompleto), e a atividade tava "Feito", muda pra "Em andamento"
    cursor.execute('UPDATE atividades SET status = "Em andamento" WHERE id = ? AND status = "Feito"', (atividade_id,))
    
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "id": novo_id})

@app.route('/api/passos/<int:id>/excluir', methods=['POST'])
def api_excluir_passo(id):
    conn = get_db_connection()
    passo = conn.execute('SELECT atividade_id FROM passos WHERE id = ?', (id,)).fetchone()
    if passo:
        conn.execute('DELETE FROM passos WHERE id = ?', (id,))
        # Verificar se agora tudo ta feito
        atividade_id = passo['atividade_id']
        todos_passos = conn.execute('SELECT concluido FROM passos WHERE atividade_id = ?', (atividade_id,)).fetchall()
        if todos_passos and all(p['concluido'] == 1 for p in todos_passos):
            conn.execute('UPDATE atividades SET status = "Feito" WHERE id = ?', (atividade_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

@app.route('/api/passos/<int:id>/atualizar', methods=['POST'])
def api_atualizar_passo(id):
    campo = request.form.get('campo')
    valor = request.form.get('valor')
    if campo in ['descricao', 'prazo']:
        conn = get_db_connection()
        conn.execute(f'UPDATE passos SET {campo} = ? WHERE id = ?', (valor, id))
        conn.commit()
        conn.close()
    return jsonify({"status": "success"})

# ─────────────────────────────────────────────
#  ATIVIDADES — CRUD
# ─────────────────────────────────────────────

from flask import jsonify

@app.route('/adicionar', methods=['POST'])
def adicionar():
    modo_origem = request.form.get('modo_origem', 'ativos')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO atividades (area, atividade, responsavel, status, data_inicio, prazo, prioridade, arquivado)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0)
    ''', (
        request.form.get('area', ''),
        request.form.get('atividade', ''),
        request.form.get('responsavel', ''),
        request.form.get('status', 'Pendente'),
        request.form.get('data_inicio', datetime.date.today().strftime('%Y-%m-%d')),
        request.form.get('prazo', datetime.date.today().strftime('%Y-%m-%d')),
        request.form.get('prioridade', 'Baixa'),
    ))
    atividade_id = cursor.lastrowid
    
    passos_desc = request.form.getlist('passos_desc[]')
    passos_prazo = request.form.getlist('passos_prazo[]')
    for desc, prazo in zip(passos_desc, passos_prazo):
        if desc.strip():
            cursor.execute(
                'INSERT INTO passos (atividade_id, descricao, prazo, concluido) VALUES (?, ?, ?, 0)',
                (atividade_id, desc.strip(), prazo.strip() if prazo.strip() else None)
            )
    conn.commit()
    conn.close()

    if modo_origem.startswith('usuario_detalhe_'):
        user_id = modo_origem.rsplit('_', 1)[-1]
        return redirect(url_for('usuario_detalhe', id=user_id))
    return redirect(url_for('index'))


@app.route('/editar/<int:id>', methods=['POST'])
def editar(id):
    conn = get_db_connection()
    conn.execute('''
        UPDATE atividades
        SET atividade   = ?,
            descricao   = ?,
            responsavel = ?,
            status      = ?,
            observacoes = ?,
            prioridade  = ?,
            data        = ?
        WHERE id = ?
    ''', (
        request.form['atividade'],
        request.form.get('descricao', ''),
        request.form['responsavel'],
        request.form['status'],
        request.form.get('observacoes', ''),
        request.form.get('prioridade', 'Baixa'),
        request.form.get('data', ''),
        id,
    ))
    conn.commit()
    conn.close()

    modo = request.form.get('modo', 'ativos')
    if modo == 'arquivados':
        return redirect(url_for('arquivados'))
    if modo.startswith('usuario_detalhe_'):
        user_id = modo.rsplit('_', 1)[-1]
        return redirect(url_for('usuario_detalhe', id=user_id))
    return redirect(url_for('index'))


@app.route('/arquivar/<int:id>', methods=['POST'])
def arquivar(id):
    conn = get_db_connection()
    conn.execute('UPDATE atividades SET arquivado = 1 WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return _redirect_back('index')


@app.route('/restaurar/<int:id>', methods=['POST'])
def restaurar(id):
    conn = get_db_connection()
    conn.execute('UPDATE atividades SET arquivado = 0 WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return _redirect_back('arquivados')


@app.route('/deletar/<int:id>', methods=['POST'])
def deletar(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM atividades WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return _redirect_back('arquivados')


# ─────────────────────────────────────────────
#  CATEGORIAS & RESPONSÁVEIS
# ─────────────────────────────────────────────

@app.route('/adicionar_categoria', methods=['POST'])
def adicionar_categoria():
    conn = get_db_connection()
    try:
        conn.execute('INSERT INTO categorias (nome, cor) VALUES (?, ?)',
                     (request.form['nome'], request.form['cor']))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()
    return redirect(url_for('configuracoes'))


@app.route('/editar_categoria/<int:id>', methods=['POST'])
def editar_categoria(id):
    conn = get_db_connection()
    conn.execute('UPDATE categorias SET nome = ?, cor = ? WHERE id = ?',
                 (request.form['nome'], request.form['cor'], id))
    conn.commit()
    conn.close()
    return redirect(url_for('configuracoes'))


@app.route('/deletar_categoria/<int:id>', methods=['POST'])
def deletar_categoria(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM categorias WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('configuracoes'))


@app.route('/adicionar_responsavel', methods=['POST'])
def adicionar_responsavel():
    conn = get_db_connection()
    try:
        conn.execute('INSERT INTO responsaveis (nome) VALUES (?)', (request.form['nome'],))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()
    return redirect(url_for('configuracoes'))


@app.route('/editar_responsavel/<int:id>', methods=['POST'])
def editar_responsavel(id):
    conn = get_db_connection()
    conn.execute('UPDATE responsaveis SET nome = ? WHERE id = ?', (request.form['nome'], id))
    conn.commit()
    conn.close()
    return redirect(url_for('configuracoes'))


@app.route('/deletar_responsavel/<int:id>', methods=['POST'])
def deletar_responsavel(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM responsaveis WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('configuracoes'))


# ─────────────────────────────────────────────
#  EXPORTAÇÃO PDF — OTIMIZADO
# ─────────────────────────────────────────────

def _criar_pdf_atividades(atividades, titulo="Relatório de Atividades"):
    """Cria um PDF otimizado em memória com tabela de atividades."""
    pdf_buffer = io.BytesIO()

    # Configuração do documento com compressão
    doc = SimpleDocTemplate(
        pdf_buffer,
        pagesize=A4,
        rightMargin=15,
        leftMargin=15,
        topMargin=15,
        bottomMargin=15,
    )

    styles = getSampleStyleSheet()
    story = []

    # Título
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#1e293b'),
        spaceAfter=12,
        alignment=1  # Centro
    )
    story.append(Paragraph(titulo, title_style))

    # Data de geração
    date_style = ParagraphStyle(
        'DateStyle',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#64748b'),
        spaceAfter=12,
        alignment=2  # Direita
    )
    story.append(Paragraph(f"Gerado em: {datetime.datetime.now().strftime('%d/%m/%Y às %H:%M')}", date_style))

    story.append(Spacer(1, 0.2 * inch))

    # Preparar dados para a tabela
    data = [['ID', 'Atividade', 'Responsável', 'Status', 'Prioridade', 'Prazo']]

    status_colors = {
        'Pendente': colors.HexColor('#fca5a5'),
        'Em andamento': colors.HexColor('#fcd34d'),
        'Feito': colors.HexColor('#a7f3d0'),
    }

    for atividade in atividades:
        data.append([
            str(atividade['id']),
            atividade['atividade'][:30] + ('...' if len(atividade['atividade']) > 30 else ''),
            atividade['responsavel'][:15],
            atividade['status'],
            atividade['prioridade'] or 'Baixa',
            atividade['prazo'] or 'N/A',
        ])

    # Criar tabela
    table = Table(data, colWidths=[0.5*inch, 1.8*inch, 1.2*inch, 1.2*inch, 0.9*inch, 0.9*inch])

    # Estilo da tabela
    table_style = TableStyle([
        # Header
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#334155')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),

        # Body
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
        ('ALIGN', (1, 1), (1, -1), 'LEFT'),
        ('VALIGN', (0, 1), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f1f5f9')]),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),

        # Status com cores
        ('BACKGROUND', (3, 1), (3, -1), colors.white),
    ])

    # Aplicar cores de status nas células
    for i, atividade in enumerate(atividades, start=1):
        status = atividade['status']
        if status in status_colors:
            table_style.add('BACKGROUND', (3, i), (3, i), status_colors[status])

    table.setStyle(table_style)
    story.append(table)

    # Resumo
    story.append(Spacer(1, 0.3 * inch))

    total = len(atividades)
    pendentes = sum(1 for a in atividades if a['status'] == 'Pendente')
    em_andamento = sum(1 for a in atividades if a['status'] == 'Em andamento')
    feitos = sum(1 for a in atividades if a['status'] == 'Feito')

    resumo_text = f"""
    <b>Resumo:</b> Total: {total} | Pendentes: {pendentes} | Em andamento: {em_andamento} | Feitos: {feitos}
    """

    resumo_style = ParagraphStyle(
        'ResumoStyle',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#475569'),
        spaceAfter=6,
        alignment=0
    )
    story.append(Paragraph(resumo_text, resumo_style))

    # Construir PDF com compressão
    doc.build(story)
    pdf_buffer.seek(0)
    return pdf_buffer


@app.route('/exportar/ativos')
def exportar_ativos():
    """Exporta atividades ativas para PDF otimizado."""
    conn = get_db_connection()
    atividades = conn.execute('SELECT * FROM atividades WHERE arquivado = 0 ORDER BY id DESC').fetchall()
    conn.close()

    pdf_buffer = _criar_pdf_atividades(atividades, "Relatório de Atividades Ativas")

    return send_file(
        pdf_buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'atividades_ativos_{datetime.date.today()}.pdf'
    )


@app.route('/exportar/arquivados')
def exportar_arquivados():
    """Exporta atividades arquivadas para PDF otimizado."""
    conn = get_db_connection()
    atividades = conn.execute('SELECT * FROM atividades WHERE arquivado = 1 ORDER BY id DESC').fetchall()
    conn.close()

    pdf_buffer = _criar_pdf_atividades(atividades, "Relatório de Atividades Arquivadas")

    return send_file(
        pdf_buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'atividades_arquivados_{datetime.date.today()}.pdf'
    )


@app.route('/exportar/usuario/<int:id>')
def exportar_usuario(id):
    """Exporta atividades de um usuário específico para PDF otimizado."""
    conn = get_db_connection()
    usuario = conn.execute('SELECT * FROM responsaveis WHERE id = ?', (id,)).fetchone()

    if not usuario:
        conn.close()
        return redirect(url_for('usuarios'))

    atividades = conn.execute(
        'SELECT * FROM atividades WHERE responsavel = ? AND arquivado = 0 ORDER BY id DESC',
        (usuario['nome'],)
    ).fetchall()
    conn.close()

    titulo = f"Relatório de Atividades - {usuario['nome']}"
    pdf_buffer = _criar_pdf_atividades(atividades, titulo)

    return send_file(
        pdf_buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'atividades_{usuario["nome"]}_{datetime.date.today()}.pdf'
    )


# ─────────────────────────────────────────────
#  PREFERÊNCIAS DE INTERFACE
# ─────────────────────────────────────────────

@app.route('/alterar-fonte/<int:tamanho>')
def alterar_fonte(tamanho):
    session['font_size'] = max(12, min(40, tamanho))
    return redirect(request.referrer or url_for('index'))


# ─────────────────────────────────────────────
#  INICIALIZAÇÃO
# ─────────────────────────────────────────────

init_db()

if __name__ == '__main__':
    import webbrowser
    from threading import Timer

    def open_browser():
        webbrowser.open_new("http://127.0.0.1:5000")

    # Garante que só abra o navegador uma vez no início,
    # ignorando as recargas do modo debug do Flask.
    if not os.environ.get("WERKZEUG_RUN_MAIN"):
        Timer(1.5, open_browser).start()

    app.run(debug=True, host='0.0.0.0', port=5000)
