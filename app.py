import os, re, sqlite3, hashlib, hmac, secrets, unicodedata
from datetime import datetime
from decimal import Decimal
from functools import wraps
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, session, flash, g

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'troque-esta-chave-antes-de-publicar')
DB_PATH = os.environ.get('DATABASE_PATH', str(Path(__file__).with_name('livraria.db')))
ESTOQUE_BAIXO = 3
ITERACOES_HASH = 200_000

PERMISSOES = {'admin': {'cadastrar', 'movimentar', 'consultar'}, 'estoquista': {'movimentar', 'consultar'}}

def conectar():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys = ON')
    return con

def hash_senha(senha, salt):
    return hashlib.pbkdf2_hmac('sha256', senha.encode(), salt, ITERACOES_HASH)

def inicializar():
    with conectar() as con:
        con.executescript('''
        CREATE TABLE IF NOT EXISTS usuarios(usuario TEXT PRIMARY KEY, salt BLOB NOT NULL, senha_hash BLOB NOT NULL, perfil TEXT NOT NULL CHECK(perfil IN ('admin','estoquista')));
        CREATE TABLE IF NOT EXISTS livros(isbn TEXT PRIMARY KEY, titulo TEXT NOT NULL, autor TEXT NOT NULL, preco_centavos INTEGER NOT NULL CHECK(preco_centavos >= 0), quantidade INTEGER NOT NULL CHECK(quantidade >= 0));
        CREATE TABLE IF NOT EXISTS movimentacoes(id INTEGER PRIMARY KEY AUTOINCREMENT, isbn TEXT NOT NULL REFERENCES livros(isbn), tipo TEXT NOT NULL, quantidade INTEGER NOT NULL, usuario TEXT NOT NULL, data_hora TEXT NOT NULL);
        ''')
        if con.execute('SELECT COUNT(*) FROM usuarios').fetchone()[0] == 0:
            for usuario, senha, perfil in [('admin','admin123','admin'),('estoque','estoque123','estoquista')]:
                salt = os.urandom(16)
                con.execute('INSERT INTO usuarios VALUES(?,?,?,?)', (usuario,salt,hash_senha(senha,salt),perfil))
            demos = [('9780000000011','Dom Casmurro','Machado de Assis',3990,12),('9780000000028','Vidas Secas','Graciliano Ramos',3490,3),('9780000000035','O Cortiço','Aluísio Azevedo',2990,0),('9780000000042','A Hora da Estrela','Clarice Lispector',3290,8),('9780000000059','Grande Sertão: Veredas','João Guimarães Rosa',6490,5)]
            con.executemany('INSERT OR IGNORE INTO livros VALUES(?,?,?,?,?)', demos)

def exigir(permissao):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if 'usuario' not in session:
                return redirect(url_for('login'))
            if permissao not in PERMISSOES.get(session.get('perfil'), set()):
                flash('Seu perfil não tem permissão para esta operação.', 'erro')
                return redirect(url_for('index'))
            return fn(*args, **kwargs)
        return wrapper
    return deco

def normalizar_isbn(valor):
    limpo = re.sub(r'[\s-]', '', valor).upper()
    if not (re.fullmatch(r'[0-9]{13}', limpo) or re.fullmatch(r'[0-9]{9}[0-9X]', limpo)):
        raise ValueError('ISBN inválido. Informe 10 ou 13 caracteres numéricos (o último pode ser X).')
    return limpo

def preco_centavos(valor):
    valor = valor.strip().replace('R$', '').replace(' ', '').replace(',', '.')
    if not re.fullmatch(r'[0-9]{1,6}(\.[0-9]{1,2})?', valor):
        raise ValueError('Preço inválido. Exemplo: 49,90.')
    n = int(Decimal(valor) * 100)
    if n <= 0: raise ValueError('O preço deve ser maior que zero.')
    return n

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        usuario = request.form.get('usuario','').strip().lower()
        senha = request.form.get('senha','')
        with conectar() as con:
            row = con.execute('SELECT salt,senha_hash,perfil FROM usuarios WHERE usuario=?',(usuario,)).fetchone()
        salt = row['salt'] if row else b'\0'*16
        valido = hmac.compare_digest(hash_senha(senha,salt), row['senha_hash'] if row else b'\0'*32)
        if row and valido:
            session.clear(); session['usuario']=usuario; session['perfil']=row['perfil']
            return redirect(url_for('index'))
        flash('Usuário ou senha incorretos.', 'erro')
    return render_template('login.html')

@app.get('/sair')
def sair():
    session.clear(); return redirect(url_for('login'))

@app.get('/')
@exigir('consultar')
def index():
    termo = request.args.get('q','').strip()
    with conectar() as con:
        livros = con.execute('SELECT * FROM livros ORDER BY titulo COLLATE NOCASE').fetchall()
        total = len(livros); baixos = sum(1 for l in livros if l['quantidade'] <= ESTOQUE_BAIXO)
        if termo:
            def norm(s): return ''.join(c for c in unicodedata.normalize('NFD',s.casefold()) if not unicodedata.combining(c))
            chave=norm(termo); livros=[l for l in livros if chave in norm(l['titulo']+' '+l['autor']) or chave.replace('-','').replace(' ','') in l['isbn']]
    return render_template('index.html', livros=livros, total=total, baixos=baixos, termo=termo)

@app.route('/cadastrar', methods=['GET','POST'])
@exigir('cadastrar')
def cadastrar():
    if request.method == 'POST':
        try:
            isbn=normalizar_isbn(request.form.get('isbn','')); titulo=request.form.get('titulo','').strip(); autor=request.form.get('autor','').strip()
            preco=preco_centavos(request.form.get('preco','')); qtd=int(request.form.get('quantidade',''))
            if len(titulo)<2 or len(autor)<2: raise ValueError('Informe título e autor com pelo menos 2 caracteres.')
            if qtd<0 or qtd>100000: raise ValueError('Quantidade deve estar entre 0 e 100000.')
            with conectar() as con:
                con.execute('INSERT INTO livros VALUES(?,?,?,?,?)',(isbn,titulo,autor,preco,qtd))
                con.execute('INSERT INTO movimentacoes(isbn,tipo,quantidade,usuario,data_hora) VALUES(?,?,?,?,?)',(isbn,'cadastro',qtd,session['usuario'],datetime.now().isoformat(timespec='seconds')))
            flash('Livro cadastrado com sucesso.','ok'); return redirect(url_for('index'))
        except (ValueError, sqlite3.IntegrityError) as e: flash(str(e) if isinstance(e,ValueError) else 'Já existe um livro com este ISBN.','erro')
    return render_template('cadastrar.html')

@app.route('/movimentar', methods=['GET','POST'])
@exigir('movimentar')
def movimentar():
    if request.method == 'POST':
        try:
            isbn=normalizar_isbn(request.form.get('isbn','')); tipo=request.form.get('tipo'); qtd=int(request.form.get('quantidade',''))
            if tipo not in ('entrada','saida') or qtd<1 or qtd>100000: raise ValueError('Informe tipo e quantidade válida (1 a 100000).')
            with conectar() as con:
                livro=con.execute('SELECT quantidade FROM livros WHERE isbn=?',(isbn,)).fetchone()
                if not livro: raise ValueError('Livro não encontrado. Confira o ISBN.')
                if tipo=='saida' and livro['quantidade']<qtd: raise ValueError(f'Estoque insuficiente. Disponível: {livro["quantidade"]}.')
                delta=qtd if tipo=='entrada' else -qtd
                con.execute('UPDATE livros SET quantidade=quantidade+? WHERE isbn=?',(delta,isbn))
                con.execute('INSERT INTO movimentacoes(isbn,tipo,quantidade,usuario,data_hora) VALUES(?,?,?,?,?)',(isbn,tipo,qtd,session['usuario'],datetime.now().isoformat(timespec='seconds')))
            flash('Movimentação registrada.','ok'); return redirect(url_for('index'))
        except (ValueError, sqlite3.IntegrityError) as e: flash(str(e),'erro')
    return render_template('movimentar.html')

@app.route('/usuarios', methods=['GET','POST'])
@exigir('cadastrar')
def usuarios():
    if request.method == 'POST':
        usuario=request.form.get('usuario','').strip().lower(); senha=request.form.get('senha',''); perfil=request.form.get('perfil')
        if not re.fullmatch(r'[a-z0-9_.-]{3,30}',usuario) or len(senha)<8 or perfil not in ('admin','estoquista'):
            flash('Usuário deve ter 3 a 30 caracteres; senha com ao menos 8; selecione um perfil.','erro')
        else:
            salt=os.urandom(16)
            try:
                with conectar() as con: con.execute('INSERT INTO usuarios VALUES(?,?,?,?)',(usuario,salt,hash_senha(senha,salt),perfil))
                flash('Usuário criado.','ok'); return redirect(url_for('index'))
            except sqlite3.IntegrityError: flash('Este usuário já existe.','erro')
    return render_template('usuarios.html')

@app.get('/saude')
def saude(): return {'status':'ok'}

inicializar()
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=int(os.environ.get('PORT',5000)), debug=False)
