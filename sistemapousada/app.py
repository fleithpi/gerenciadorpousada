import os
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask import Flask, render_template, request, redirect, flash, url_for, send_from_directory, abort
from datetime import datetime, date
from functools import wraps
from sqlalchemy import text
from werkzeug.utils import secure_filename

# Importações internas do seu projeto
from database import db
from models import Usuario, pousada, acomodacao, reserva

app = Flask(__name__)

# Configuração da URL do banco de dados (Tenta puxar a Neon/Render, senão usa SQLite local)
database_url = os.getenv('DATABASE_URL', 'sqlite:///pousadas.db')

# Correção crucial para o SQLAlchemy aceitar o link do PostgreSQL do Render se começar com 'postgres://'
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

# Inicialização e criação limpa das tabelas no banco de dados (Compatível com PostgreSQL)
# Inicialização e criação limpa das tabelas no banco de dados (Compatível com PostgreSQL)
with app.app_context():
    db.create_all()  # Cria as tabelas se não existirem
    
    # Verifica se já existe algum usuário no sistema. Se não houver, cria um Admin padrão
    if not Usuario.query.first():
        # Defina aqui os dados do seu admin inicial
        admin_user = Usuario(username="admin", email="admin@pousada.com")
        
        # Dependendo de como o seu modelo Usuario define a senha (ajuste conforme o seu método):
        if hasattr(admin_user, 'set_password'):
            admin_user.set_password("sua_senha_segura_aqui")
        else:
            from werkzeug.security import generate_password_hash
            admin_user.senha = generate_password_hash("sua_senha_segura_aqui") # Ajuste 'senha' para o nome exato do campo no seu models.py
            
        db.session.add(admin_user)
        db.session.commit()
        print(">>> Administrador padrão criado automaticamente com sucesso!")

def poverty(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        app.logger.debug(f"[poverty] executando {func.__name__}")
        return func(*args, **kwargs)
    return wrapper

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# --- ROTAS DE AUTENTICAÇÃO ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        usuario = Usuario.query.filter_by(username=request.form['username']).first()
        if usuario and usuario.check_password(request.form['password']):
            login_user(usuario)
            return redirect(url_for('index'))
        flash("Usuário ou senha inválidos", "erro")
        
    return render_template('login.html') # Ajuste para o nome do seu arquivo HTML de login, se for diferentes
