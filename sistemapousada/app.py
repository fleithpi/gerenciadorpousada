import os
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask import Flask, render_template, request, redirect, flash, url_for, send_from_directory, abort
from datetime import datetime, date, timedelta
from functools import wraps
from sqlalchemy import text
from werkzeug.security import generate_password_hash, check_password_hash
from uuid import uuid4

# Importações internas do seu projeto
from sistemapousada.database import db
from sistemapousada.models import Usuario, pousada, acomodacao, reserva

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_templates = os.path.join(BASE_DIR, 'templates')
if not os.path.isdir(_templates):
    _templates = os.path.join(BASE_DIR, 'sistemapousada', 'templates')

app = Flask(__name__, template_folder=_templates)

# Configuração da URL do banco de dados 
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
    
    # Migração automática: adiciona a coluna email na tabela usuario se não existir
    try:
        db.session.execute(text("ALTER TABLE usuario ADD COLUMN email VARCHAR(120);"))
        db.session.commit()
    except Exception:
        db.session.rollback()

    # Migração automática: adiciona a coluna usuario_id na tabela pousada se não existir
    try:
        db.session.execute(text("ALTER TABLE pousada ADD COLUMN usuario_id INTEGER;"))
        db.session.commit()
    except Exception:
        db.session.rollback()
    
    # Cria um Admin padrão se não existir nenhum utilizador
    if not Usuario.query.first():
        admin_user = Usuario(username="admin", email="admin@pousada.com", role="admin")
        
        if hasattr(admin_user, 'set_password'):
            admin_user.set_password("sua_senha_segura_aqui")
        else:
            admin_user.senha = generate_password_hash("sua_senha_segura_aqui")
            
        db.session.add(admin_user)
        db.session.commit()
        
        # Cria uma pousada padrão para o admin inicial se ele não tiver nenhuma
        if not pousada.query.filter_by(usuario_id=admin_user.id).first():
            pousada_padrao = pousada(nome="Pousada Principal", usuario_id=admin_user.id)
            db.session.add(pousada_padrao)
            db.session.commit()

        print(">>> Administrador e Pousada padrão criados automaticamente com sucesso!")

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def reserva_do_usuario(reserva_id):
    return reserva.query.join(acomodacao).join(pousada).filter(
        reserva.id == reserva_id,
        pousada.usuario_id == current_user.id
    ).first_or_404()


# --- ROTA PRINCIPAL (Isolada por utilizador com métricas e gráficos) ---

@app.route('/')
@login_required
def index():
    try:
        # Busca apenas as pousadas pertencentes ao administrador logado
        minhas_pousadas = pousada.query.filter_by(usuario_id=current_user.id).all()
        pousada_ids = [p.id for p in minhas_pousadas]
        
        # Filtra as acomodações apenas das pousadas deste admin
        acomodacoes = acomodacao.query.filter(acomodacao.pousada_id.in_(pousada_ids)).all() if pousada_ids else []
        acomodacao_ids = [a.id for a in acomodacoes]
        
        # Filtra apenas as reservas associadas às acomodações deste admin
        reservas = reserva.query.filter(reserva.acomodacao_id.in_(acomodacao_ids)).all() if acomodacao_ids else []
            
        # Métricas para os cards do topo do painel
        total_pousadas = len(minhas_pousadas)
        total_acomodacoes = len(acomodacoes)
        total_reservas = len(reservas)
        
        # Dados para o gráfico de barras (Chart.js)
        chart_labels = []
        chart_values = []
        for p in minhas_pousadas:
            chart_labels.append(p.nome)
            count_res = reserva.query.join(acomodacao).filter(acomodacao.pousada_id == p.id).count()
            chart_values.append(count_res)

        return render_template(
            'index.html', 
            pousadas=minhas_pousadas, 
            acomodacoes=acomodacoes, 
            reservas=reservas,
            total_pousadas=total_pousadas,
            total_acomodacoes=total_acomodacoes,
            total_reservas=total_reservas,
            chart_labels=chart_labels,
            chart_values=chart_values
        )
    except Exception as e:
        app.logger.error(f"Erro na rota index: {e}")
        flash(f"Erro ao carregar painel: {e}", "erro")
        return render_template('index.html', pousadas=[], acomodacoes=[], reservas=[], total_pousadas=0, total_acomodacoes=0, total_reservas=0, chart_labels=[], chart_values=[])


# --- ROTAS DE AUTENTICAÇÃO E CADASTRO ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        login_input = request.form['username']
        senha_input = request.form['password']
        
        usuario = Usuario.query.filter(
            (Usuario.username == login_input) | (Usuario.email == login_input)
        ).first()
        
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
        
        user_existente = Usuario.query.filter(
            (Usuario.email == email) | (Usuario.username == username)
        ).first()
        
        if user_existente:
            flash("Este e-mail ou nome de usuário já está em uso.", "erro")
            return redirect(url_for('register'))
            
        novo_usuario = Usuario(username=username, email=email, role='admin')
        
        if hasattr(novo_usuario, 'set_password'):
            novo_usuario.set_password(password)
        else:
            novo_usuario.senha = generate_password_hash(password)
            
        try:
            db.session.add(novo_usuario)
            db.session.flush()  # gera o id sem fechar a transação

            # Cria automaticamente uma Pousada exclusiva para este novo dono
            nova_pousada = pousada(
                nome=f"Pousada de {username}",
                usuario_id=novo_usuario.id
            )
            db.session.add(nova_pousada)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Erro ao cadastrar usuário: {e}")
            flash("Não foi possível criar a conta. Tente novamente.", "erro")
            return redirect(url_for('register'))

        flash("Conta e Pousada criadas com sucesso! Faça o login.", "sucesso")
        return redirect(url_for('login'))
        
    return render_template('registrar.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# --- ROTAS DE CRIAÇÃO E GESTÃO DE RESERVAS ---

@app.route('/reservar', methods=['POST'])
@login_required
def reservar():
    try:
        # CONVERTE O ID PARA INTEIRO AQUI
        acomodacao_id_raw = request.form.get('acomodacao_id')
        if not acomodacao_id_raw:
            flash("Selecione uma acomodação válida.", "erro")
            return redirect(url_for('index'))
            
        acomodacao_id = int(acomodacao_id_raw) 
        
        hospede_nome = request.form.get('hospede') or request.form.get('hospede_nome')
        data_entrada_str = request.form.get('data_entrada')
        data_saida_str = request.form.get('data_saida')
        
        try:
            data_entrada = datetime.strptime(data_entrada_str, '%Y-%m-%d').date()
            data_saida = datetime.strptime(data_saida_str, '%Y-%m-%d').date()
        except ValueError:
            flash("Formato de data inválido.", "erro")
            return redirect(url_for('index'))

        if data_entrada >= data_saida:
            flash("A data de check-out deve ser posterior à data de check-in.", "erro")
            return redirect(url_for('index'))

        # Valida disponibilidade
        if not reserva.verificar_disponibilidade(acomodacao_id, data_entrada, data_saida):
            flash("Acomodação indisponível para o período selecionado.", "erro")
            return redirect(url_for('index'))

        acomod_obj = acomodacao.query.get_or_404(acomodacao_id)
        pousada_pertence = pousada.query.filter_by(id=acomod_obj.pousada_id, usuario_id=current_user.id).first()
        if not pousada_pertence:
            flash("Acomodação inválida.", "erro")
            return redirect(url_for('index'))

        dias = (data_saida - data_entrada).days
        valor_total = dias * acomod_obj.preco_diaria

        nova_reserva = reserva(
            acomodacao_id=acomodacao_id,
            hospede_nome=hospede_nome,
            data_entrada=data_entrada,
            data_saida=data_saida,
            valor_total=float(valor_total)
        )
        
        db.session.add(nova_reserva)
        db.session.commit()
        flash("Reserva criada com sucesso!", "sucesso")
    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao criar reserva: {e}", "erro")
        
    return redirect(url_for('index'))

@app.route('/editar_reserva/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_reserva(id):
    reserva_item = reserva.query.get_or_404(id)
    pousada_pertence = pousada.query.filter_by(id=reserva_item.acomodacao.pousada_id, usuario_id=current_user.id).first()
    if not pousada_pertence:
        abort(403)
    
    if request.method == 'POST':
        reserva_item.hospede_nome = request.form.get('hospede') or request.form.get('hospede_nome', reserva_item.hospede_nome)
        db.session.commit()
        flash("Reserva atualizada com sucesso!", "sucesso")
        return redirect(url_for('index'))
        
    return render_template('editar_reserva.html', reserva=reserva_item)

@app.route('/remover-reserva/<int:reserva_id>', methods=['GET', 'POST'])
@login_required
def remover_reserva(reserva_id):
    reserva_item = reserva.query.get_or_404(reserva_id)
    pousada_pertence = pousada.query.filter_by(id=reserva_item.acomodacao.pousada_id, usuario_id=current_user.id).first()
    if not pousada_pertence:
        abort(403)
    
    try:
        db.session.delete(reserva_item)
        db.session.commit()
        flash("Reserva removida com sucesso!", "sucesso")
    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao remover reserva: {e}", "erro")
        
    return redirect(url_for('index'))


# --- ROTAS DE GESTÃO DE ACOMODAÇÕES ---

@app.route('/adicionar-acomodacao', methods=['POST'])
@login_required
def adicionar_acomodacao():
    try:
        pousada_id_raw = request.form.get('pousada_id')
        if not pousada_id_raw:
            flash("Selecione uma pousada válida.", "erro")
            return redirect(url_for('index'))
            
        pousada_id = int(pousada_id_raw)
        nome_numero = request.form.get('nome_numero')
        tipo = request.form.get('tipo')
        preco_diaria_str = request.form.get('preco_diaria')
        
        pousada_pertence = pousada.query.filter_by(id=pousada_id, usuario_id=current_user.id).first()
        if not pousada_pertence:
            flash("Acesso negado ou pousada inválida.", "erro")
            return redirect(url_for('index'))
            
        try:
            preco_diaria = float(preco_diaria_str)
        except (ValueError, TypeError):
            preco_diaria = 0.0

        nova_acomod = acomodacao(
            pousada_id=pousada_id,
            nome_numero=nome_numero,
            tipo=tipo,
            preco_diaria=preco_diaria
        )
        
        db.session.add(nova_acomod)
        db.session.commit()
        flash("Acomodação cadastrada com sucesso!", "sucesso")
    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao cadastrar acomodação: {e}", "erro")
        
    return redirect(url_for('index'))

@app.route('/remover-acomodacao/<int:acomodacao_id>', methods=['GET', 'POST'])
@login_required
def remover_acomodacao(acomodacao_id):
    acomodacao_item = acomodacao.query.get_or_404(acomodacao_id)
    pousada_pertence = pousada.query.filter_by(id=acomodacao_item.pousada_id, usuario_id=current_user.id).first()
    if not pousada_pertence:
        flash("Acesso negado.", "erro")
        return redirect(url_for('index'))
    
    try:
        # Remove primeiro as reservas associadas para evitar conflito de chave estrangeira
        reserva.query.filter_by(acomodacao_id=acomodacao_item.id).delete()
        db.session.delete(acomodacao_item)
        db.session.commit()
        flash("Acomodação removida com sucesso!", "sucesso")
    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao remover acomodação: {e}", "erro")
        
    return redirect(url_for('index'))


# --- ROTAS DE CRIAÇÃO DE POUSADAS ---

@app.route('/adicionar-pousada', methods=['POST'])
@login_required
def adicionar_pousada():
    nome = request.form.get('nome')
    if not nome:
        flash("O nome da pousada é obrigatório.", "erro")
        return redirect(url_for('index'))
        
    nova_pousada = pousada(
        nome=nome,
        usuario_id=current_user.id
    )
    db.session.add(nova_pousada)
    db.session.commit()
    flash("Pousada cadastrada com sucesso!", "sucesso")
    return redirect(url_for('index'))


# --- ROTAS AUXILIARES DO MENU (Evitam erros 404/500 ao clicar nos atalhos) ---

@app.route('/seed')
@login_required
def seed():
    try:
        # Cria dados de exemplo para o utilizador atual se desejar
        p_exemplo = pousada.query.filter_by(usuario_id=current_user.id).first()
        if not p_exemplo:
            p_exemplo = pousada(nome="Pousada Exemplo", usuario_id=current_user.id)
            db.session.add(p_exemplo)
            db.session.commit()
            
        if not acomodacao.query.filter_by(pousada_id=p_exemplo.id).first():
            ac_exemplo = acomodacao(pousada_id=p_exemplo.id, nome_numero="Quarto 101", tipo="quarto", preco_diaria=150.0)
            db.session.add(ac_exemplo)
            db.session.commit()
            
        flash("Dados de exemplo carregados com sucesso!", "sucesso")
    except Exception as e:
        flash(f"Erro ao popular dados: {e}", "erro")
    return redirect(url_for('index'))

@app.route('/reservas')
@login_required
def gerenciar_reservas():
    return redirect(url_for('index'))

@app.route('/pagamento')
@login_required
def gerenciar_pagamentos():
    minhas_pousadas = pousada.query.filter_by(usuario_id=current_user.id).all()
    pousada_ids = [item.id for item in minhas_pousadas]
    acomodacao_ids = [
        item.id for item in acomodacao.query.filter(
            acomodacao.pousada_id.in_(pousada_ids)
        ).all()
    ] if pousada_ids else []
    reservas_usuario = reserva.query.filter(
        reserva.acomodacao_id.in_(acomodacao_ids)
    ).all() if acomodacao_ids else []
    return render_template('pagamento.html', reservas=reservas_usuario)

@app.route('/confirmar-pagamento/<int:reserva_id>', methods=['POST'])
@login_required
def confirmar_pagamento(reserva_id):
    reserva_item = reserva_do_usuario(reserva_id)
    arquivo = request.files.get('comprovante')
    if not arquivo or not arquivo.filename:
        flash("Selecione um arquivo PDF para enviar.", "erro")
        return redirect(url_for('gerenciar_pagamentos'))
    if not allowed_file(arquivo.filename) or arquivo.stream.read(5) != b'%PDF-':
        flash("O comprovante deve ser um arquivo PDF válido.", "erro")
        return redirect(url_for('gerenciar_pagamentos'))

    arquivo.stream.seek(0)
    nome_arquivo = f"{uuid4().hex}.pdf"
    caminho_arquivo = os.path.join(app.config['UPLOAD_FOLDER'], nome_arquivo)
    arquivo.save(caminho_arquivo)

    comprovante_anterior = reserva_item.comprovante_pagamento
    reserva_item.comprovante_pagamento = nome_arquivo
    reserva_item.pagamento_confirmado = True
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        if os.path.exists(caminho_arquivo):
            os.remove(caminho_arquivo)
        app.logger.exception("Erro ao salvar comprovante de pagamento")
        flash("Não foi possível salvar o comprovante. Tente novamente.", "erro")
        return redirect(url_for('gerenciar_pagamentos'))

    if comprovante_anterior:
        caminho_anterior = os.path.join(
            app.config['UPLOAD_FOLDER'], os.path.basename(comprovante_anterior)
        )
        if os.path.isfile(caminho_anterior):
            os.remove(caminho_anterior)
    flash("Comprovante enviado e pagamento confirmado.", "sucesso")
    return redirect(url_for('gerenciar_pagamentos'))

@app.route('/comprovantes/<filename>')
@login_required
def download_comprovante(filename):
    comprovante = reserva.query.join(acomodacao).join(pousada).filter(
        reserva.comprovante_pagamento == filename,
        pousada.usuario_id == current_user.id
    ).first_or_404()
    return send_from_directory(
        app.config['UPLOAD_FOLDER'],
        comprovante.comprovante_pagamento,
        as_attachment=True
    )

@app.route('/remover-confirmacao-pagamento/<int:reserva_id>', methods=['POST'])
@login_required
def remover_confirmacao_pagamento(reserva_id):
    reserva_item = reserva_do_usuario(reserva_id)
    comprovante = reserva_item.comprovante_pagamento
    reserva_item.pagamento_confirmado = False
    reserva_item.comprovante_pagamento = None
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception("Erro ao remover confirmação de pagamento")
        flash("Não foi possível remover a confirmação. Tente novamente.", "erro")
        return redirect(url_for('gerenciar_pagamentos'))

    if comprovante:
        caminho_arquivo = os.path.join(
            app.config['UPLOAD_FOLDER'], os.path.basename(comprovante)
        )
        if os.path.isfile(caminho_arquivo):
            os.remove(caminho_arquivo)
    flash("Confirmação de pagamento removida.", "sucesso")
    return redirect(url_for('gerenciar_pagamentos'))