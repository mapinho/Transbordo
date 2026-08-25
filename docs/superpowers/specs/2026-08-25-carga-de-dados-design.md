# Carga de Dados por planilha (Django + HTMX)

## Contexto e objetivo

O stack Django já tem as cinco grades editáveis de um cenário e a tela de Cenários, mas **não tem
nenhum caminho para dados entrarem no sistema**. A tela de Cenários só cria por clonagem, e a
ferramenta de espelhamento (`apps/simulacao/legado.py`, spec de 2026-08-24) é explicitamente uma ponte
de desenvolvimento: bloqueia com `DEBUG` desligado e lê de um banco legado que não existirá em
produção.

Isto significa que hoje uma cooperativa nova em produção é um beco sem saída: sem cenário não há onde
importar, e sem importar não há como criar o primeiro cenário. Esta fase fecha esse círculo.

O stack Streamlit resolve isso com quatro uploads de Excel (`data_loader.py`). Esta fase porta essa
capacidade, corrigindo as fraquezas que o levantamento expôs.

## Levantamento do legado

Quatro importadores em `data_loader.py`, todos com semântica de **UPSERT** por nome dentro do cenário:

| função | linha | aba correspondente | chave do upsert |
|---|---:|---|---|
| `load_factories` | 240 | Fábricas | `(cenario_id, nome)` |
| `load_warehouses` | 297 | Armazéns | `(cenario_id, nome)` |
| `load_routes` | 348 | Rotas | `(cenario_id, armazem_id, fabrica_id)` |
| `load_previsoes` | 413 | Previsões | `(fabrica_id ou armazem_id, mes_referencia)` |

### Fraquezas que esta fase corrige

**1. Os erros são invisíveis.** Todos os quatro coletam linhas ruins numa lista `erros` e a despejam
num `logging.warning` (`data_loader.py:288-292`). O usuário vê "116 importadas" e nunca descobre quais
três falharam nem por quê. Em `load_previsoes` é pior: uma entidade que não casa com nenhuma fábrica
nem armazém só incrementa `skipped`, sem registro algum.

**2. Não há pré-visualização.** O import escreve direto. Numa operação que sobrescreve dados de um
cenário inteiro, não há como ver o estrago antes de causá-lo.

**3. A ordem entre arquivos é conhecimento tácito.** Rotas e Previsões resolvem fábricas e armazéns por
nome. Subir Rotas antes de Armazéns rejeita todas as linhas, e nada na tela diz isso.

**4. Safras não têm caminho de importação.** A grade de Datas de Safra existe nos dois stacks, mas
nenhum dos quatro importadores as traz — elas só entram por digitação ou clonagem. Num tenant novo, são
19 janelas para digitar à mão (uma por unidade, nos dados atuais) logo após importar todo o resto.

**5. Colisão de nome resolve em silêncio.** `load_previsoes` procura a entidade primeiro entre as
fábricas, depois entre os armazéns (`data_loader.py:439-453`). Um nome que exista nos dois vai para a
fábrica sem aviso.

## Escopo

**Dentro:**
- Módulo `apps/simulacao/planilha.py`: `analisar` (puro) e `aplicar` (escrita).
- Uma pasta `.xlsx` única com **cinco abas** — Fábricas, Armazéns, Rotas, Previsões, Safras.
- Telas de upload e de pré-visualização, com confirmação explícita.
- Criação de cenário a partir da própria tela de carga, incluindo o primeiro da cooperativa.
- Geração do template a partir das definições de coluna que as grades já usam.
- Emenda à sequência de fases da spec de arquitetura, que hoje não contempla esta fase.

**Fora:**
- Aposentar os quatro `.xlsx` em `templates/`, que servem o stack Streamlit e continuam válidos lá.
- Importação assíncrona. As planilhas reais têm ~1.000 linhas; o parse é de segundos. Se algum dia
  passarem de dezenas de milhares, isto vira trabalho para a fila da fase Procrastinate.
- Exportação para Excel (o caminho inverso).
- Varredura periódica de arquivos de upload abandonados (ver §Riscos).
- Qualquer mudança nos importadores do `data_loader.py` legado.

## Decisões de arquitetura

### 1. Fronteira `analisar` / `aplicar`

Duas funções em `apps/simulacao/planilha.py`:

- `analisar(arquivo, cenario) -> Relatorio` — lê a pasta, consulta o banco para resolver nomes e para
  distinguir criação de atualização, e classifica cada linha. **Não escreve nada.**
- `aplicar(arquivo, cenario) -> Relatorio` — chama `analisar`, grava as linhas válidas dentro de um
  único `transaction.atomic()`, devolve o mesmo relatório.

**`cenario` é opcional em `analisar`.** No caso de bootstrap, o usuário nomeia um cenário que ainda não
existe, e a pré-visualização precisa rodar antes de qualquer escrita — inclusive antes de criar o
cenário. Com `cenario=None`, o lado-banco da resolução é vazio: nada existe para atualizar, tudo é
criação, e os nomes resolvem apenas contra a própria pasta (§3). Só `aplicar` cria o cenário, e o cria
dentro da mesma transação que grava as linhas — de modo que uma pasta com erro fatal não deixe um
cenário vazio para trás.

É a mesma fronteira que `legado.py` adotou (`ler_legado`/`escrever`) e pelo mesmo motivo: concentra a
lógica não-trivial num lado testável isoladamente.

### 2. Pré-visualizar, depois confirmar, reanalisando o arquivo

O upload guarda o `.xlsx` no storage do servidor sob um token e mostra a pré-visualização. Confirmar
**reanalisa o mesmo arquivo** e aplica.

Alternativas descartadas:
- **Serializar o parse na sessão Django** — evitaria a reanálise, mas duplicaria os dados e obrigaria a
  sessão (backend de banco) a carregar ~500 linhas de previsões por upload.
- **Tabela de staging** — auditável e robusta a reinício, mas adiciona modelo, migration e limpeza de
  registros abandonados para um fluxo que dura segundos.

Como `analisar` é determinística e o arquivo é a única fonte, o relatório da confirmação é idêntico ao
que o usuário aprovou. O arquivo é apagado depois de aplicado.

### 3. Resolução de nomes contra o banco **e** contra a própria pasta

Esta é a decisão que faz o bootstrap funcionar, e é fácil de errar.

Rotas, Previsões e Safras referenciam fábricas e armazéns por nome. Num cenário **vazio** — exatamente o
caso da carga inicial — resolver apenas contra o banco rejeitaria todas as rotas, porque as fábricas
ainda não existem. A resolução tem que ser contra:

> (o que já está no banco para este cenário) ∪ (o que as abas anteriores desta mesma pasta vão criar)

As abas são processadas em ordem de dependência: **Fábricas → Armazéns → Rotas → Previsões → Safras**.
Sem isso, o recurso nasce incapaz de fazer a única coisa para a qual foi criado.

### 4. Colisão de nome é rejeição, não escolha silenciosa

Se um nome resolver para uma fábrica **e** para um armazém do mesmo cenário, a linha é rejeitada como
ambígua, nomeando as duas unidades. O legado escolhe a fábrica sem avisar
(`data_loader.py:439-453`); com pré-visualização, tornar o conflito visível custa nada e evita um dado
errado que ninguém notaria.

### 5. Validação em vocabulário de planilha, com `full_clean()` como rede

O parser valida e reporta em coordenadas que quem edita o Excel reconhece: aba, número da linha, nome da
coluna, valor recebido. Antes de salvar, `aplicar` chama `full_clean()` em cada instância.

Alternativas descartadas:
- **`forms.Form` por linha** — daria mensagens e validadores prontos, mas instanciar um Form por linha
  para 476 previsões é desajeitado, e a parte que mais dói (resolver a entidade contra outras abas e
  contra o banco) é validação entre linhas, que Form nenhum resolve sozinho; metade da validação ficaria
  fora dele.
- **Só `full_clean()`** — as mensagens sairiam em linguagem de modelo ("Este campo não pode ser nulo"),
  que não diz ao usuário qual célula corrigir.

O `full_clean()` fica como rede de segurança contra assimetrias entre o que o parser aceita e o que o
modelo permite. Essa assimetria não é hipotética: foi exatamente o defeito dos floats nuláveis achado na
revisão da fase de espelhamento.

### 6. Linha ruim não aborta a pasta

Mantém a tolerância do legado: linhas inválidas são rejeitadas individualmente e as válidas seguem. A
diferença é que agora as rejeitadas aparecem na tela antes de qualquer escrita, e o usuário decide se
confirma assim ou corrige e reenvia.

Um erro **estrutural** aborta a pasta inteira e não oferece confirmação, porque nesse caso não há nada
confiável a mostrar. São três, e apenas três: o arquivo não é um `.xlsx` legível; nenhuma das cinco abas
reconhecidas está presente; ou uma aba presente tem cabeçalho irreconhecível. Aba simplesmente ausente
**não** é erro estrutural — ver §Formato.

### 7. O cenário pode nascer na própria tela de carga

A tela aceita um cenário existente **ou** um nome novo. Quando o cenário é criado e é o primeiro da
cooperativa, nasce com `is_oficial=True`.

Alternativas descartadas:
- **A tela de Cenários ganhar "criar vazio"** — manteria a carga com responsabilidade única, mas
  espalha o bootstrap por duas telas quando ele é uma operação só.
- **Management command de provisionamento** — exigiria acesso ao servidor para onboardar cada
  cooperativa nova, o que contraria o rumo de produto multi-cooperativa.

### 8. Template gerado, não pré-fabricado

A tela oferece o download de uma pasta modelo com as cinco abas e seus cabeçalhos, **gerada na hora a
partir das mesmas definições de coluna que as grades consomem** (`apps/simulacao/columns.py`), mais o
mapeamento de §Formato. Os quatro `.xlsx` em `templates/` são artefatos estáticos que envelhecem em
silêncio quando o schema muda; gerar elimina a categoria de bug.

## Formato da pasta

Cabeçalhos na primeira linha, comparados sem diferenciar maiúsculas nem espaços nas pontas — o legado já
normaliza assim (`df.columns = [str(col).strip().lower() ...]`).

**Fábricas** — `nome`, `capacidade_estatica`, `capacidade_esmagamento_diaria`,
`capacidade_recebimento_diaria`, `limite_caminhoes`, `carga_media_caminhao`, `estoque_inicial`.
Todos os numéricos são obrigatórios; célula em branco rejeita a linha (é a correção do bug A8 da Fase 1,
onde `NaN` do pandas chegava ao Postgres como número válido).

**Armazéns** — `nome`, `capacidade_estatica`, `capacidade_expedicao_diaria`, `estoque_inicial`. Todos os
numéricos obrigatórios.

**Rotas** — `origem` (armazém), `destino` (fábrica), `distancia_km`, `custo_frete_ton`,
`custo_frete_entressafra`. Quando `custo_frete_entressafra` vem em branco, assume o valor de
`custo_frete_ton`, como o legado faz (`data_loader.py:386-387`).

**Previsões** — `entidade` (nome de uma fábrica ou de um armazém), `mes_referencia`,
`recebimento_produtor`, `vendas`. `mes_referencia` é normalizado para o primeiro dia do mês.
`recebimento_produtor` e `vendas` em branco valem 0.

**Safras** — `unidade` (nome de uma fábrica ou de um armazém), `data_inicio`, `data_fim`. O
`entidade_tipo` é **derivado** da resolução, não informado pelo usuário: se o nome resolve para armazém,
grava `'Armazém'`; se resolve para fábrica, grava `'Fábrica'`. É a convenção que
`views.py::safras_grid` e `services.clone_scenario` já assumem. Datas em `YYYY-MM-DD`.

Uma aba ausente **não** é erro se não houver nada a importar nela: uma pasta só com Fábricas e Armazéns
é válida. O que é erro é uma aba presente com cabeçalho irreconhecível.

## O relatório

`analisar` devolve, por aba: quantas linhas serão criadas, quantas atualizadas, e a lista das
rejeitadas. Cada rejeição carrega a aba, o número da linha **como aparece no Excel**, o motivo em
português e os valores da linha, para o usuário reconhecer o registro. Mais um campo de erro estrutural
que, quando preenchido, significa que nada pode ser aplicado.

## Fluxo e URLs

- `GET /simulacao/carga/` — formulário: cenário (existente ou nome novo) e arquivo. Link para baixar o
  template.
- `POST /simulacao/carga/` — guarda o arquivo sob um token, redireciona.
- `GET /simulacao/carga/<token>/` — pré-visualização (o relatório).
- `POST /simulacao/carga/<token>/` — aplica, apaga o arquivo, redireciona para as grades do cenário.
- `GET /simulacao/carga/template/` — a pasta modelo gerada.

Tudo com `login_required`, e o cenário-alvo validado como pertencente à cooperativa do usuário, como as
demais views já fazem.

## Testes

O parser é exercitado com `.xlsx` montados em memória via openpyxl, sem fixture em disco:

- Linha válida em cada uma das cinco abas.
- Campo numérico obrigatório em branco rejeita a linha e nomeia a coluna.
- Rota cujo armazém é criado **na mesma pasta** resolve (o caso do §3, o bootstrap).
- Entidade que não resolve para nada é rejeitada com motivo, não silenciosamente pulada.
- Nome que resolve para fábrica **e** armazém é rejeitado como ambíguo.
- `mes_referencia` não parseável rejeita a linha sem abortar a aba.
- Aba ausente é aceita; cabeçalho irreconhecível é erro estrutural.
- `analisar` não escreve nada (contagens do banco inalteradas depois de chamá-la).
- `aplicar` é consistente com o relatório que `analisar` produziu.

Nas views: pré-visualização não escreve; confirmar escreve; criar o primeiro cenário da cooperativa o
marca oficial; um cenário de outra cooperativa não é alcançável.

## Verificação

Além da suíte: gerar o template pela tela, preencher com os dados reais de uma cooperativa, importar num
cenário novo, e conferir que as cinco grades mostram o mesmo que o espelhamento produziu a partir do
banco legado. É a checagem cruzada mais forte disponível — dois caminhos independentes para o mesmo
destino.

## Emenda ao roteiro

A sequência de 8 fases da spec de arquitetura (2026-08-22) não contempla esta fase. Ela entra entre a
fase 3 (UI) e a fase 4 (Procrastinate), pois a otimização não tem o que otimizar sem dados carregados.

## Decisões em aberto / riscos

- **Arquivos de upload abandonados.** Um usuário que envia uma pasta e nunca confirma deixa o `.xlsx` no
  storage. Cada novo upload do mesmo usuário substitui o anterior, e aplicar apaga; o resíduo é o caso
  do usuário que sobe uma vez e desiste. Deliberadamente sem varredura periódica agora — quando houver
  fila (fase Procrastinate), é uma task de manutenção de três linhas.
- **Tamanho de upload.** Sem limite explícito além do `DATA_UPLOAD_MAX_MEMORY_SIZE` padrão do Django
  (2,5 MB), que acomoda folgadamente as ~1.000 linhas reais. Uma pasta maior falha com o erro padrão do
  Django, que é claro o suficiente.
- **UPSERT não apaga.** Como no legado, importar uma pasta sem uma fábrica que existe no cenário **não**
  a remove. Quem quiser remover usa a grade. Isso é deliberado: uma planilha parcial não deve poder
  destruir dados que ela simplesmente não menciona.
- **A ordem das abas é a ordem de dependência, e é imposta pelo código, não pelo arquivo.** Se algum dia
  uma aba nova referenciar outra, ela precisa entrar na posição certa da sequência — não basta
  acrescentá-la ao final.
