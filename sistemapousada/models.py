from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sistemapousada.database import db

class Usuario(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200)), nullable=False

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
                              
class pousada(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    acomodacoes = db.relationship('acomodacao', backref='pousada', lazy=True)

class acomodacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pousada_id = db.Column(db.Integer, db.ForeignKey('pousada.id'), nullable=False)
    nome_numero = db.Column(db.String(50), nullable=False)
    tipo = db.Column(db.String(20), nullable=False) # 'casa' ou 'quarto'
    preco_diaria = db.Column(db.Float, nullable=False)

class reserva(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    acomodacao_id = db.Column(db.Integer, db.ForeignKey('acomodacao.id'), nullable=False)
    acomodacao = db.relationship('acomodacao', backref='reservas', lazy=True)
    hospede_nome = db.Column(db.String(100), nullable=False)
    data_entrada = db.Column(db.Date, nullable=False)
    data_saida = db.Column(db.Date, nullable=False)
    valor_total = db.Column(db.Float, nullable=False)
    checkin_confirmado = db.Column(db.Boolean, default=False, nullable=False)
    checkout_confirmado = db.Column(db.Boolean, default=False, nullable=False)
    pagamento_confirmado = db.Column(db.Boolean, default=False, nullable=False)
    comprovante_pagamento = db.Column(db.String(200), nullable=True)
    pagamento_confirmado = db.Column(db.Boolean, default=False, nullable=False)

    @staticmethod
    def verificar_disponibilidade(acomodacao_id, entrada, saida):
        # Lógica matemática: verifica se as datas se cruzam
        conflito = reserva.query.filter(
            reserva.acomodacao_id == acomodacao_id,
            entrada < reserva.data_saida,
            saida > reserva.data_entrada
        ).first()
        return conflito is None # Retorna True se estiver livre
