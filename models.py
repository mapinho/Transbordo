import datetime
from typing import Optional

from sqlalchemy import Column, Integer, String, Float, ForeignKey, Date, DateTime, Boolean
from sqlalchemy.orm import Mapped, declarative_base, relationship

Base = declarative_base()

class Cenario(Base):
    __tablename__ = 'cenarios'

    id: Mapped[int] = Column(Integer, primary_key=True, info={'label': 'ID', 'type': 'number', 'format': '%d', 'disabled': True})
    nome: Mapped[str] = Column(String(100), unique=True, nullable=False, info={'label': 'Nome do Cenário'})
    data_criacao: Mapped[Optional[datetime.datetime]] = Column(DateTime, default=datetime.datetime.now, info={'label': 'Data de Criação', 'type': 'date', 'disabled': True})
    is_oficial: Mapped[Optional[bool]] = Column(Boolean, default=False, info={'hidden': True})

class Fabrica(Base):
    __tablename__ = 'fabricas'

    id: Mapped[int] = Column(Integer, primary_key=True, info={'label': 'id', 'type': 'number', 'format': '%d', 'disabled': True})
    cenario_id: Mapped[int] = Column(Integer, ForeignKey('cenarios.id', ondelete='CASCADE'), nullable=False, info={'hidden': True})
    nome: Mapped[str] = Column(String(100), nullable=False, info={'label': 'Fábrica', 'disabled': True})
    capacidade_estatica: Mapped[float] = Column(Float, nullable=False, info={'label': 'Capacidade Estática (Ton)', 'type': 'number', 'format': 'localized', 'step': 1})
    capacidade_esmagamento_diaria: Mapped[float] = Column(Float, nullable=False, info={'label': 'Esmagamento Diário (Ton)', 'type': 'number', 'format': 'localized', 'step': 1})
    capacidade_recebimento_diaria: Mapped[float] = Column(Float, nullable=False, info={'label': 'Recebimento Diário (Ton)', 'type': 'number', 'format': 'localized', 'step': 1})
    limite_caminhoes: Mapped[int] = Column(Integer, nullable=False, info={'label': 'Limite de Caminhões', 'type': 'number', 'format': 'localized', 'step': 1})
    carga_media_caminhao: Mapped[float] = Column(Float, nullable=False, info={'label': 'Carga Média (Ton)', 'type': 'number', 'format': 'localized', 'step': 1})
    estoque_inicial: Mapped[float] = Column(Float, nullable=False, info={'label': 'Estoque Inicial (Ton)', 'type': 'number', 'format': 'localized', 'step': 1})

    previsoes = relationship("PrevisaoFabrica", back_populates="fabrica", cascade="all, delete-orphan")
    rotas = relationship("Rota", back_populates="fabrica", cascade="all")

class Armazem(Base):
    __tablename__ = 'armazens'

    id: Mapped[int] = Column(Integer, primary_key=True, info={'label': 'id', 'type': 'number', 'format': '%d', 'disabled': True})
    cenario_id: Mapped[int] = Column(Integer, ForeignKey('cenarios.id', ondelete='CASCADE'), nullable=False, info={'hidden': True})
    nome: Mapped[str] = Column(String(100), nullable=False, info={'label': 'Armazém', 'disabled': True})
    capacidade_estatica: Mapped[float] = Column(Float, nullable=False, info={'label': 'Capacidade Estática (Ton)', 'type': 'number', 'format': 'localized', 'step': 0.1})
    capacidade_expedicao_diaria: Mapped[float] = Column(Float, nullable=False, info={'label': 'Expedição Diária (Ton)', 'type': 'number', 'format': 'localized', 'step': 0.1})
    estoque_inicial: Mapped[float] = Column(Float, nullable=False, info={'label': 'Estoque Inicial (Ton)', 'type': 'number', 'format': 'localized', 'step': 0.1})

    previsoes = relationship("PrevisaoArmazem", back_populates="armazem", cascade="all, delete-orphan")
    rotas = relationship("Rota", back_populates="armazem", cascade="all")

class Rota(Base):
    __tablename__ = 'rotas'

    id: Mapped[int] = Column(Integer, primary_key=True, info={'label': 'id', 'type': 'number', 'format': '%d', 'disabled': True})
    cenario_id: Mapped[int] = Column(Integer, ForeignKey('cenarios.id', ondelete='CASCADE'), nullable=False, info={'hidden': True})
    armazem_id: Mapped[int] = Column(Integer, ForeignKey('armazens.id', ondelete='CASCADE'), nullable=False, info={'hidden': True})
    fabrica_id: Mapped[int] = Column(Integer, ForeignKey('fabricas.id', ondelete='CASCADE'), nullable=False, info={'hidden': True})
    distancia_km: Mapped[float] = Column(Float, nullable=False, info={'label': 'Distância (km)', 'type': 'number', 'format': 'localized', 'step': 1})
    custo_frete_ton: Mapped[float] = Column(Float, nullable=False, info={'label': 'Custo Safra (R$/Ton)', 'type': 'number', 'format': 'localized', 'step': 0.01})
    custo_frete_entressafra: Mapped[float] = Column(Float, nullable=False, default=0, info={'label': 'Custo Entressafra (R$/Ton)', 'type': 'number', 'format': 'localized', 'step': 0.01})

    armazem = relationship("Armazem", back_populates="rotas")
    fabrica = relationship("Fabrica", back_populates="rotas")

class PrevisaoFabrica(Base):
    __tablename__ = 'previsoes_fabrica'

    id: Mapped[int] = Column(Integer, primary_key=True, info={'label': 'id', 'type': 'number', 'format': '%d', 'disabled': True})
    fabrica_id: Mapped[int] = Column(Integer, ForeignKey('fabricas.id', ondelete='CASCADE'), nullable=False, info={'hidden': True})
    mes_referencia: Mapped[datetime.date] = Column(Date, nullable=False, info={'label': 'Mês', 'type': 'date', 'disabled': True})
    recebimento_produtor: Mapped[Optional[float]] = Column(Float, default=0, info={'label': 'Recebimento Produtor (Ton)', 'type': 'number', 'format': 'localized', 'step': 0.1})
    vendas: Mapped[Optional[float]] = Column(Float, default=0, info={'label': 'Vendas (Ton)', 'type': 'number', 'format': 'localized', 'step': 0.1})

    fabrica = relationship("Fabrica", back_populates="previsoes")

class PrevisaoArmazem(Base):
    __tablename__ = 'previsoes_armazem'

    id: Mapped[int] = Column(Integer, primary_key=True, info={'label': 'id', 'type': 'number', 'format': '%d', 'step': 1, 'disabled': True})
    armazem_id: Mapped[int] = Column(Integer, ForeignKey('armazens.id', ondelete='CASCADE'), nullable=False, info={'hidden': True})
    mes_referencia: Mapped[datetime.date] = Column(Date, nullable=False, info={'label': 'Mês', 'type': 'date', 'disabled': True})
    recebimento_produtor: Mapped[Optional[float]] = Column(Float, default=0, info={'label': 'Recebimento Produtor (Ton)', 'type': 'number', 'format': 'localized', 'step': 0.1})
    vendas: Mapped[Optional[float]] = Column(Float, default=0, info={'label': 'Vendas (Ton)', 'type': 'number', 'format': 'localized', 'step': 0.1})

    armazem = relationship("Armazem", back_populates="previsoes")

class SafraUnidade(Base):
    __tablename__ = 'safras_unidades'

    id: Mapped[int] = Column(Integer, primary_key=True, info={'label': 'id', 'type': 'number', 'format': '%d', 'disabled': True})
    cenario_id: Mapped[int] = Column(Integer, ForeignKey('cenarios.id', ondelete='CASCADE'), nullable=False, info={'hidden': True})
    entidade_tipo: Mapped[str] = Column(String(20), nullable=False, info={'label': 'Tipo', 'disabled': True})
    entidade_id: Mapped[int] = Column(Integer, nullable=False, info={'hidden': True})
    data_inicio: Mapped[datetime.date] = Column(Date, nullable=False, info={'label': 'Início', 'type': 'date'})
    data_fim: Mapped[datetime.date] = Column(Date, nullable=False, info={'label': 'Fim', 'type': 'date'})

class MovimentacaoDiaria(Base):
    __tablename__ = 'movimentacoes_diarias'

    id: Mapped[int] = Column(Integer, primary_key=True, info={'label': 'id', 'type': 'number', 'format': '%d', 'disabled': True})
    cenario_id: Mapped[int] = Column(Integer, ForeignKey('cenarios.id', ondelete='CASCADE'), nullable=False, info={'hidden': True})
    data: Mapped[datetime.date] = Column(Date, nullable=False, info={'label': 'Data', 'type': 'date'})
    armazem_id: Mapped[int] = Column(Integer, ForeignKey('armazens.id', ondelete='CASCADE'), nullable=False, info={'hidden': True})
    fabrica_id: Mapped[int] = Column(Integer, ForeignKey('fabricas.id', ondelete='CASCADE'), nullable=False, info={'hidden': True})
    quantidade_ton: Mapped[float] = Column(Float, nullable=False, info={'label': 'Quantidade (Ton)', 'type': 'number', 'format': 'localized', 'step': 0.01})
    custo_total: Mapped[float] = Column(Float, nullable=False, info={'label': 'Custo Total (R$)', 'type': 'number', 'format': 'localized', 'step': 0.01})

class LogExecucao(Base):
    __tablename__ = 'logs_execucao'

    id: Mapped[int] = Column(Integer, primary_key=True)
    data_execucao: Mapped[Optional[datetime.datetime]] = Column(DateTime, default=datetime.datetime.now)
    status: Mapped[Optional[str]] = Column(String(50))
    mensagem: Mapped[Optional[str]] = Column(String(500))

class ResumoMensalFabrica(Base):
    __tablename__ = 'resumo_mensal_fabrica'

    id: Mapped[int] = Column(Integer, primary_key=True, info={'hidden': True})
    cenario_id: Mapped[int] = Column(Integer, ForeignKey('cenarios.id', ondelete='CASCADE'), nullable=False, info={'hidden': True})
    mes: Mapped[str] = Column(String(7), nullable=False, info={'label': 'Mês'}) # 'YYYY-MM'
    fabrica_id: Mapped[int] = Column(Integer, ForeignKey('fabricas.id', ondelete='CASCADE'), nullable=False, info={'hidden': True})
    rec_produtor: Mapped[Optional[float]] = Column(Float, default=0, info={'label': 'Recebimento Produtor (Ton)', 'type': 'number', 'format': 'localized', 'step': 0.01})
    rec_transbordo: Mapped[Optional[float]] = Column(Float, default=0, info={'label': 'Recebimento Transbordo (Ton)', 'type': 'number', 'format': 'localized', 'step': 0.01})
    esmagado: Mapped[Optional[float]] = Column(Float, default=0, info={'label': 'Esmagado (Ton)', 'type': 'number', 'format': 'localized', 'step': 0.01})
    saldo_estoque: Mapped[Optional[float]] = Column(Float, default=0, info={'label': 'Saldo Estoque (Ton)', 'type': 'number', 'format': 'localized', 'step': 0.01})
    capacidade_estatica: Mapped[Optional[float]] = Column(Float, default=0, info={'label': 'Capacidade Estática (Ton)', 'type': 'number', 'format': 'localized', 'step': 0.01})
    excedente: Mapped[Optional[float]] = Column(Float, default=0, info={'label': 'Excedente (Ton)', 'type': 'number', 'format': 'localized', 'step': 0.01})

class ResumoMensalArmazem(Base):
    __tablename__ = 'resumo_mensal_armazem'

    id: Mapped[int] = Column(Integer, primary_key=True, info={'hidden': True})
    cenario_id: Mapped[int] = Column(Integer, ForeignKey('cenarios.id', ondelete='CASCADE'), nullable=False, info={'hidden': True})
    mes: Mapped[str] = Column(String(7), nullable=False, info={'label': 'Mês'}) # 'YYYY-MM'
    armazem_id: Mapped[int] = Column(Integer, ForeignKey('armazens.id', ondelete='CASCADE'), nullable=False, info={'hidden': True})
    rec_produtor: Mapped[Optional[float]] = Column(Float, default=0, info={'label': 'Recebimento Produtor (Ton)', 'type': 'number', 'format': 'localized', 'step': 0.01})
    envio_transbordo: Mapped[Optional[float]] = Column(Float, default=0, info={'label': 'Envio Transbordo (Ton)', 'type': 'number', 'format': 'localized', 'step': 0.01})
    vendas: Mapped[Optional[float]] = Column(Float, default=0, info={'label': 'Vendas (Ton)', 'type': 'number', 'format': 'localized', 'step': 0.01})
    saldo_estoque: Mapped[Optional[float]] = Column(Float, default=0, info={'label': 'Saldo Estoque (Ton)', 'type': 'number', 'format': 'localized', 'step': 0.01})
    capacidade_estatica: Mapped[Optional[float]] = Column(Float, default=0, info={'label': 'Capacidade Estática (Ton)', 'type': 'number', 'format': 'localized', 'step': 0.01})
    excedente: Mapped[Optional[float]] = Column(Float, default=0, info={'label': 'Excedente (Ton)', 'type': 'number', 'format': 'localized', 'step': 0.01})
