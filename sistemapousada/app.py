import os
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask import Flask, render_template, request, redirect, flash, url_for, send_from_directory, abort
from datetime import datetime, date
from functools import wraps
from sqlalchemy import text
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

# Importações internas do seu projeto
from sistemapousada.database import db
from sistemapousada.models import Usuario, pousada, acomodacao, reserva

app = Flask(__name__)

# Configuração da URL do banco de dados 
# (Usa SQLite localmente se DATABASE_URL não estiver definida, ou PostgreSQL no Render/Neon)
database_url = os.getenv('DATABASE_URL', 'sqlite:///pousadas.db')

if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'chave_secreta_para_alertas')

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Por favor, faça o login para acessar esta página."
login_manager.login_message_category = "erro"

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

# Criar pastas necessárias para uploads
try:
    os.makedirs(app.instance_path, exist_ok=True)
    app.config['UPLOAD_FOLDER'] = os.path.join(app.instance_path, 'uploads')
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
except Exception as e:
    app.logger.warning(f"Não foi possível criar pasta de uploads: {e}")
    app.config['UPLOAD_FOLDER'] = '/tmp/uploads'
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ALLOWED_EXTENSIONS = {'pdf'}
db.init_app(app)

# Inicialização e criação limpa das tabelas no banco de dados
with app.app_context():
    db.create_all()  
    
    # Verifica se já existe algum usuário no sistema. Se não houver, cria um Admin padrão
    if not Usuario.query.first():
        admin_user = Usuario(username="admin", email="admin@pousada.com")
        
        if hasattr(admin_user, 'set_password'):
            admin_user.set_password("sua_senha_segura_aqui")
        else:
            admin_user.senha = generate_password_hash("sua_senha_segura_aqui")
            
        db.session.add(admin_user)
        db.session.commit()
        print(">>> Administrador padrão criado automaticamente com sucesso!")

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# --- ROTAS DE AUTENTICAÇÃO E CADASTRO ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        login_input = request.form['username'] # Pode ser o username ou o e-mail
        senha_input = request.form['password']
        
        # Procura por username ou email
        usuario = Usuario.query.filter(
            (Usuario.username == login_input) | (Usuario.email == login_input)
        ).first()
        
        # Validação da senha (suporta método do model ou verificação direta do hash)
        senha_valida = False
        if usuario:
            if hasattr(usuario, 'check_password'):
                senha_valida = usuario.check_password(senha_input)
            else:
                senha_valida = check_password_hash(usuario.senha, senha_input)
                
        if usuario and senha_valida:
            login_user(usuario)
            return redirect(url_for('index'))
            
        flash("E-mail/Usuário ou senha inválidos", "erro")
        
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Verifica se o e-mail ou username já existem
        user_existente = Usuario.query.filter(
            (Usuario.email == email) | (Usuario.username == username)
        ).first()
        
        if user_existente:
            flash("Este e-mail ou nome de usuário já está em uso.", "erro")
            return redirect(url_for('register'))
            
        novo_usuario = Usuario(username=username, email=email)
        
        if hasattr(novo_usuario, 'set_password'):
            novo_usuario.set_password(password)
        else:
            novo_usuario.senha = generate_password_hash(password)
            
        db.session.add(novo_usuario)
        db.session.commit()
        
        flash("Cadastro realizado com sucesso! Faça o login.", "sucesso")
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))
