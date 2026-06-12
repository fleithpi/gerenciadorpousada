import os
from flask import Flask, render_template, request, redirect, flash, url_for, send_from_directory, abort
from datetime import datetime, date
from functools import wraps
from sqlalchemy import text
from werkzeug.utils import secure_filename
from sistemapusada.database import db
from sistemapousada.models import pousada, acomodacao, reserva

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///pousadas.db')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'chave_secreta_para_alertas')

# Criar pastas necessárias
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

# Criar o banco de dados automaticamente ao iniciar
with app.app_context():
    db.create_all()
    existing_columns = [row[1] for row in db.session.execute(text("PRAGMA table_info(reserva)")).fetchall()]
    if 'checkin_confirmado' not in existing_columns:
        db.session.execute(text("ALTER TABLE reserva ADD COLUMN checkin_confirmado BOOLEAN NOT NULL DEFAULT 0"))
    if 'checkout_confirmado' not in existing_columns:
        db.session.execute(text("ALTER TABLE reserva ADD COLUMN checkout_confirmado BOOLEAN NOT NULL DEFAULT 0"))
    if 'pagamento_confirmado' not in existing_columns:
        db.session.execute(text("ALTER TABLE reserva ADD COLUMN pagamento_confirmado BOOLEAN NOT NULL DEFAULT 0"))
    if 'comprovante_pagamento' not in existing_columns:
        db.session.execute(text("ALTER TABLE reserva ADD COLUMN comprovante_pagamento TEXT"))
    db.session.commit()


def poverty(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        app.logger.debug(f"[poverty] executando {func.__name__}")
        return func(*args, **kwargs)
    return wrapper

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    pousadas = pousada.query.all()
    acomodacoes = acomodacao.query.all()
    reservas = reserva.query.all()

    total_pousadas = len(pousadas)
    total_acomodacoes = len(acomodacoes)
    total_reservas = len(reservas)

    reservas_por_pousada = {}
    for r in reservas:
        nome_pousada = r.acomodacao.pousada.nome if r.acomodacao and r.acomodacao.pousada else "Desconhecida"
        reservas_por_pousada[nome_pousada] = reservas_por_pousada.get(nome_pousada, 0) + 1

    chart_labels = list(reservas_por_pousada.keys())
    chart_values = list(reservas_por_pousada.values())

    return render_template(
        'index.html',
        pousadas=pousadas,
        acomodacoes=acomodacoes,
        reservas=reservas,
        total_pousadas=total_pousadas,
        total_acomodacoes=total_acomodacoes,
        total_reservas=total_reservas,
        chart_labels=chart_labels,
        chart_values=chart_values
    )

@app.route('/reservas')
def reservas_page():
    pousadas = pousada.query.all()
    acomodacoes = acomodacao.query.all()
    reservas = reserva.query.all()

    total_pousadas = len(pousadas)
    total_acomodacoes = len(acomodacoes)
    total_reservas = len(reservas)
    total_valor_reservas = sum(r.valor_total for r in reservas)

    reservas_por_pousada = {}
    for r in reservas:
        nome_pousada = r.acomodacao.pousada.nome if r.acomodacao and r.acomodacao.pousada else "Desconhecida"
        reservas_por_pousada[nome_pousada] = reservas_por_pousada.get(nome_pousada, 0) + 1

    chart_labels = list(reservas_por_pousada.keys())
    chart_values = list(reservas_por_pousada.values())

    return render_template(
        'reservas.html',
        pousadas=pousadas,
        acomodacoes=acomodacoes,
        reservas=reservas,
        total_pousadas=total_pousadas,
        total_acomodacoes=total_acomodacoes,
        total_reservas=total_reservas,
        total_valor_reservas=total_valor_reservas,
        chart_labels=chart_labels,
        chart_values=chart_values
    )

@app.route('/reservar', methods=['POST'])
@poverty
def reservar():
    acomodacao_id = int(request.form['acomodacao_id'])
    hospede = request.form['hospede']
    
    # Converte as strings de data vindas do HTML em objetos Date do Python
    entrada = datetime.strptime(request.form['data_entrada'], '%Y-%m-%d').date()
    saida = datetime.strptime(request.form['data_saida'], '%Y-%m-%d').date()

    if entrada >= saida:
        flash("A data de saída deve ser maior que a data de entrada!", "erro")
        return redirect(url_for('index'))

    # Verifica se a acomodação está livre
    if not reserva.verificar_disponibilidade(acomodacao_id, entrada, saida):
        flash("Desculpe, este quarto/casa já está alugado neste período!", "erro")
        return redirect(url_for('index'))

    # Calcula o valor total
    acomodacao_obj = acomodacao.query.get(acomodacao_id)
    diarias = (saida - entrada).days
    valor_total = diarias * acomodacao_obj.preco_diaria

    # Salva no banco
    nova_reserva = reserva(
        acomodacao_id=acomodacao_id, hospede_nome=hospede,
        data_entrada=entrada, data_saida=saida, valor_total=valor_total
    )
    db.session.add(nova_reserva)
    db.session.commit()
    
    flash(f"Reserva realizada com sucesso! Total: R$ {valor_total:.2f}", "sucesso")
    return redirect(url_for('reservas_page'))

@app.route('/remover-reserva/<int:reserva_id>')
@poverty
def remover_reserva(reserva_id):
    reserva_obj = reserva.query.get(reserva_id)
    if reserva_obj:
        db.session.delete(reserva_obj)
        db.session.commit()
        flash("Reserva removida com sucesso.", "sucesso")
    else:
        flash("Reserva não encontrada.", "erro")
    return redirect(url_for('reservas_page'))

@app.route('/confirmar-checkin/<int:reserva_id>')
@poverty
def confirmar_checkin(reserva_id):
    reserva_obj = reserva.query.get(reserva_id)
    if reserva_obj:
        reserva_obj.checkin_confirmado = True
        db.session.commit()
        flash("Check-in confirmado com sucesso.", "sucesso")
    else:
        flash("Reserva não encontrada.", "erro")
    return redirect(url_for('reservas_page'))

@app.route('/confirmar-checkout/<int:reserva_id>')
@poverty
def confirmar_checkout(reserva_id):
    reserva_obj = reserva.query.get(reserva_id)
    if reserva_obj:
        reserva_obj.checkout_confirmado = True
        db.session.commit()
        flash("Check-out confirmado com sucesso.", "sucesso")
    else:
        flash("Reserva não encontrada.", "erro")
    return redirect(url_for('reservas_page'))

@app.route('/confirmar-pagamento/<int:reserva_id>', methods=['POST'])
@poverty
def confirmar_pagamento(reserva_id):
    reserva_obj = reserva.query.get(reserva_id)
    if not reserva_obj:
        flash("Reserva não encontrada.", "erro")
        return redirect(url_for('reservas_page'))

    file = request.files.get('comprovante')
    if not file or file.filename == '':
        flash("Envie um arquivo PDF para confirmar o pagamento.", "erro")
        return redirect(url_for('reservas_page'))
    if not allowed_file(file.filename):
        flash("O comprovante deve ser um arquivo PDF.", "erro")
        return redirect(url_for('reservas_page'))

    filename = secure_filename(file.filename)
    save_name = f"reserva_{reserva_id}_{filename}"
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], save_name))

    reserva_obj.pagamento_confirmado = True
    reserva_obj.comprovante_pagamento = save_name
    db.session.commit()
    flash("Pagamento confirmado com comprovante PDF.", "sucesso")
    return redirect(url_for('reservas_page'))

@app.route('/comprovante/<filename>')
def download_comprovante(filename):
    filename = secure_filename(filename)
    if not filename:
        abort(404)
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)
@app.route('/remover-confirmacao-checkin/<int:reserva_id>')
@poverty
def remover_confirmacao_checkin(reserva_id):
    reserva_obj = reserva.query.get(reserva_id)
    if reserva_obj:
        reserva_obj.checkin_confirmado = False
        db.session.commit()
        flash("Confirmação de check-in removida.", "sucesso")
    else:
        flash("Reserva não encontrada.", "erro")
    return redirect(url_for('reservas_page'))

@app.route('/remover-confirmacao-checkout/<int:reserva_id>')
@poverty
def remover_confirmacao_checkout(reserva_id):
    reserva_obj = reserva.query.get(reserva_id)
    if reserva_obj:
        reserva_obj.checkout_confirmado = False
        db.session.commit()
        flash("Confirmação de check-out removida.", "sucesso")
    else:
        flash("Reserva não encontrada.", "erro")
    return redirect(url_for('reservas_page'))

@app.route('/remover-confirmacao-pagamento/<int:reserva_id>')
@poverty
def remover_confirmacao_pagamento(reserva_id):
    reserva_obj = reserva.query.get(reserva_id)
    if reserva_obj:
        # remove stored PDF file if exists
        if reserva_obj.comprovante_pagamento:
            try:
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], reserva_obj.comprovante_pagamento)
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception:
                app.logger.exception("Erro ao remover arquivo de comprovante")
        reserva_obj.pagamento_confirmado = False
        reserva_obj.comprovante_pagamento = None
        db.session.commit()
        flash("Confirmação de pagamento removida.", "sucesso")
    else:
        flash("Reserva não encontrada.", "erro")
    return redirect(url_for('reservas_page'))


@app.route('/pagamento')
def pagamento_page():
    reservas = reserva.query.order_by(reserva.data_entrada.desc()).all()
    return render_template('pagamento.html', reservas=reservas)

@app.route('/adicionar-acomodacao', methods=['POST'])
@poverty
def adicionar_acomodacao():
    try:
        pousada_id = int(request.form['pousada_id'])
        nome_numero = request.form['nome_numero'].strip()
        tipo = request.form['tipo']
        preco_diaria = float(request.form['preco_diaria'])

        if not nome_numero or preco_diaria <= 0:
            raise ValueError

        nova_acomodacao = acomodacao(
            pousada_id=pousada_id,
            nome_numero=nome_numero,
            tipo=tipo,
            preco_diaria=preco_diaria
        )
        db.session.add(nova_acomodacao)
        db.session.commit()
        flash("Acomodação adicionada com sucesso!", "sucesso")
    except (ValueError, KeyError):
        flash("Preencha corretamente todos os campos da acomodação.", "erro")
    return redirect(url_for('index'))

@app.route('/adicionar-pousada', methods=['POST'])
@poverty
def adicionar_pousada():
    nome = request.form.get('nome', '').strip()
    if not nome:
        flash("O nome da pousada é obrigatório.", "erro")
        return redirect(url_for('index'))

    nova_pousada = pousada(nome=nome)
    db.session.add(nova_pousada)
    db.session.commit()
    flash("Pousada adicionada com sucesso!", "sucesso")
    return redirect(url_for('index'))

@app.route('/remover-acomodacao/<int:acomodacao_id>')
@poverty
def remover_acomodacao(acomodacao_id):
    acomodacao_obj = acomodacao.query.get(acomodacao_id)
    if acomodacao_obj:
        if acomodacao_obj.reservas:
            flash("Não é possível remover acomodação com reservas ativas.", "erro")
        else:
            db.session.delete(acomodacao_obj)
            db.session.commit()
            flash("Acomodação removida com sucesso.", "sucesso")
    else:
        flash("Acomodação não encontrada.", "erro")
    return redirect(url_for('index'))

# ROTA AUXILIAR: Acesse uma vez no navegador para criar dados de teste
@app.route('/seed')
def seed():
    if not pousada.query.first():
        p1 = pousada(nome="Pousada do Sol (Centro)")
        p2 = pousada(nome="Pousada Maré Alta (Beira-Mar)")
        db.session.add_all([p1, p2])
        db.session.commit()

        a1 = acomodacao(pousada_id=p1.id, nome_numero="Quarto 101 Luxury", tipo="quarto", preco_diaria=250.0)
        a2 = acomodacao(pousada_id=p1.id, nome_numero="Casa de Campo Master", tipo="casa", preco_diaria=600.0)
        a3 = acomodacao(pousada_id=p2.id, nome_numero="Chalé Frente Mar 01", tipo="casa", preco_diaria=450.0)
        db.session.add_all([a1, a2, a3])
        db.session.commit()
        return "Banco de dados populado com sucesso!"
    return "O banco já possui dados."

if __name__ == '__main__':
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode, host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
