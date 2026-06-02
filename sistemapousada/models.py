from database import db

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

    @staticmethod
    def verificar_disponibilidade(acomodacao_id, entrada, saida):
        # Lógica matemática: verifica se as datas se cruzam
        conflito = reserva.query.filter(
            reserva.acomodacao_id == acomodacao_id,
            entrada < reserva.data_saida,
            saida > reserva.data_entrada
        ).first()
        return conflito is None # Retorna True se estiver livre