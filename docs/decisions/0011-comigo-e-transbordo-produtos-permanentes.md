# 11. Comigo e Transbordo: dois produtos permanentes independentes

Data: 2026-08-30
Status: Aceito

## Contexto

O roteiro da migração Django (`docs/superpowers/specs/2026-08-22-fase5-arquitetura-saas-django.md` §11)
previa um "Cutover": desligar o Streamlit, migrar o cliente para o Django e **congelar** o `Comigo.git`.

Na prática isso não aconteceu. O `Comigo.git` está em produção em `comigo.vectorconsulting.com.br`
com vhost, configuração e banco próprios; o `Transbordo.git` está em produção em
`transbordo.vectorconsulting.com.br`, também com infra e banco próprios e independentes. Os dados de
desenvolvimento do Transbordo vieram da base de produção do Comigo (espelhamento da Fase 5).

## Decisão

Comigo e Transbordo são **dois produtos em produção, independentes e permanentes**. O cliente usa os
dois: o Comigo continua servindo, com **desenvolvimento congelado** (nenhuma alteração nova) mas **sem
ser desligado**; a evolução do produto acontece só no Transbordo. Os dois repositórios e as duas infra
não interferem entre si.

Consequência para a "Fase 11": ela deixa de ser "migração de cliente / desligar Streamlit" e passa a
ser apenas **higiene deste repositório** — remover o código do stack Streamlit/SQLAlchemy que aqui é
peso morto (o Streamlit real é o Comigo.git) — mais a carga do banco de produção do Transbordo (espelho
do dev) e o versionamento `1.0.0`.

## Consequências

- O `Especificacao_Sistema_Transbordo_Atualizada.md` permanece como spec funcional do domínio.
- `mcp_server.py` continua no repo (cliente stdio da Face JSON, ADR 0010).
- Nenhuma mudança é feita no `Comigo.git`.
- Não há janela de rollback a preservar no cutover: os dois produtos já são produção estável à parte.
