# Espelhamento de dados do banco legado para o schema Django

## Contexto e objetivo

A etapa "UI: Dados & Cenários" (spec de 2026-08-23) entregou as cinco grades editáveis do lado Django,
com 178 testes verdes. Mas o banco de desenvolvimento Django (`transbordo`) tem zero linhas de
`Cenario`: a tela de Cenários só cria **por clonagem** (`apps/simulacao/views.py`, `cenarios_list`
exige `origem_id`) e a Carga de Dados por Excel está explicitamente fora do escopo daquela fase. Não há
como bootstrapar o cenário oficial pela UI, e portanto nenhuma das cinco grades pode ser exercitada de
verdade — a prova que temos delas é só de teste.

O banco legado `comigo`, que serve o stack Streamlit/SQLAlchemy, tem dados reais da cooperativa. Esta
etapa constrói uma ferramenta de desenvolvimento que espelha esses dados para o schema Django,
atribuindo-os a um tenant, para que as telas já construídas possam ser exercitadas contra dados de
produção — e para que as fases seguintes (Dashboard, Carga de Dados, Otimização) tenham massa real
disponível desde o primeiro dia.

**Isto não é o cutover de produção.** É uma ponte de desenvolvimento com prazo de validade: morre
quando o stack Streamlit for aposentado e o banco `comigo` deixar de ser fonte.

## Levantamento do banco legado

Ambos os bancos vivem no mesmo Postgres local (`localhost:5432`): `comigo` (legado, variáveis `DB_*` /
`DATABASE_URL`) e `transbordo` (Django, variáveis `DJANGO_DB_*`). A separação deliberada dessas
variáveis está no [ADR 0002](../../decisions/0002-settings-por-ambiente.md).

Contagens verificadas em 2026-08-24:

| tabela legada | linhas | espelhada? |
|---|---:|---|
| `cenarios` | 7 | sim |
| `fabricas` | 14 | sim |
| `armazens` | 119 | sim |
| `rotas` | 238 | sim |
| `previsoes_fabrica` | 56 | sim |
| `previsoes_armazem` | 476 | sim |
| `safras_unidades` | 133 | sim |
| `movimentacoes_diarias` | 13.299 | não |
| `resumo_mensal_armazem` | 1.598 | não |
| `resumo_mensal_fabrica` | 188 | não |
| `logs_execucao` | 6 | não |
| `daily_log_factories`, `daily_log_warehouses`, `freight_transfers` | 0 | não (tabelas mortas) |

Total espelhado: ~1.043 linhas.

Os dados são coerentes entre si: 7 cenários × 2 fábricas = 14; 7 × 17 armazéns = 119; 7 × (2 × 17)
rotas = 238; 4 meses de previsão por unidade (14 × 4 = 56, 119 × 4 = 476); 7 × 19 unidades = 133 safras.

### Dois achados que esta investigação produziu

**A pendência A11 da Fase 1 está de fato resolvida.** `CLAUDE.md` lista como tarefa manual pendente
confirmar que não há linhas `cenario_id IS NULL` antes de aplicar o `ALTER TABLE ... SET NOT NULL`. A
verificação foi feita nas **7 tabelas**, todas com **zero** nulos: `fabricas` (0/14), `armazens`
(0/119), `rotas` (0/238), `safras_unidades` (0/133), `movimentacoes_diarias` (0/13299),
`resumo_mensal_fabrica` (0/188) e `resumo_mensal_armazem` (0/1598). Ressalva: isso foi medido no banco
`comigo` local, que não é necessariamente a instância de produção a que a pendência A11 se refere — a
mesma consulta precisa ser repetida lá antes de migrar.

**O port Django das Previsões está fiel ao schema real, e isso não era óbvio.**
`previsoes_fabrica` e `previsoes_armazem` **não têm coluna `cenario_id`** no banco real — penduram
apenas em `fabrica_id`/`armazem_id`, e o escopo por cenário vem indiretamente, porque a própria fábrica
é clonada por cenário. É exatamente o que `apps/simulacao/models.py` faz ao declará-las
`CooperativaScopedModel` em vez de `CenarioScopedModel`, e o que `models.py` (legado) também declara.
Os três estão de acordo; nenhuma tradução especial é necessária no espelhamento.

**Encoding:** o banco é UTF-8 e os dados estão limpos (`JATAÍ`, `CINQUENTÃO`, `Estática` verificados por
codepoint). O mojibake visível ao inspecionar via terminal do Windows é artefato do console, não dos
dados. Nenhum tratamento de encoding é necessário.

## Escopo

**Dentro:**
- Módulo `apps/simulacao/legado.py` com a leitura e a escrita separadas.
- Management command `espelhar_legado`.
- Testes da lógica de escrita, sem dependência do banco legado.

**Fora:**
- Tabelas de saída da otimização (`movimentacoes_diarias`, `resumo_mensal_*`, `logs_execucao`). São
  regeneráveis pelo `engine.py` portado, nenhuma tela Django as lê ainda, e espelhá-las seria copiar
  resultados que o port do engine deveria ser capaz de reproduzir sozinho. Entram na fase do Dashboard,
  se entrarem.
- Criação de usuários e manejo de senha.
- Cutover de produção, migração inversa (Django → legado), e sincronização contínua entre os bancos.

## Decisões de arquitetura

### 1. Leitura reusa o ORM SQLAlchemy legado

`ler_legado` faz `from models import Cenario, Fabrica, ...` (módulo da raiz, que é livre de Streamlit) e
monta a própria engine a partir de `DATABASE_URL`. Deliberadamente **não** usa
`data_loader.get_engine()`, que importa Streamlit e chama `st.error`.

Alternativas descartadas:
- **SQL bruto via psycopg** — autocontido e imune a refactor dos dois lados, mas duplicaria a declaração
  de um schema que `models.py` já declara uma vez.
- **Segundo `DATABASES` no Django + models unmanaged via `inspectdb`** — adicionaria entrada permanente
  de configuração e um router de banco para servir uma ferramenta temporária, e contraria o ADR 0002,
  que separou `DJANGO_DB_*` de `DB_*` precisamente para os dois stacks nunca se cruzarem na config.

O acoplamento aos módulos da raiz é real, mas tem o mesmo prazo de validade da ferramenta: quando o
stack Streamlit morrer, o banco `comigo` deixa de ser fonte e o comando morre junto.

### 2. Fronteira entre leitura e escrita, para testabilidade

Duas funções de responsabilidade única em `apps/simulacao/legado.py`:

- `abrir_sessao_legado(database_url) -> Session` — constrói a engine SQLAlchemy sobre o banco legado.
- `ler_legado(session) -> DadosLegado` — recebe uma sessão já aberta e devolve uma dataclass com listas
  de dicts puros. Não conhece Django.
- `escrever(dados, cooperativa) -> dict[str, int]` — recebe essas listas, escreve no schema Django,
  devolve contagens por tabela (das linhas efetivamente escritas). Não conhece SQLAlchemy.

A sessão é **injetada** em `ler_legado` em vez de a função construir a própria engine a partir da URL:
uma URL de SQLite em memória cria um banco novo e vazio a cada conexão, então a versão que constrói a
própria engine seria intestável sem um Postgres legado à disposição. Com a sessão injetada, os testes
usam o mesmo padrão que `tests/conftest.py` já emprega.

Toda a lógica não-trivial (remapeamento de IDs, ordem de inserção, apagamento) mora em `escrever`, que é
testável com dicts montados à mão. **Os testes não precisam do banco `comigo`** — o que importa porque
`comigo` é um banco local e não versionado, indisponível na CI. `ler_legado` fica reduzida a sete
queries triviais (uma por tabela espelhada), que a verificação manual cobre.

### 3. Idempotência por apagar-e-recarregar o tenant

Cada execução apaga tudo do tenant alvo e reinsere do zero, deixando o Django gerar IDs novos.

Alternativas descartadas:
- **Preservar os IDs do legado** — tornaria `SafraUnidade.entidade_id` válido sem remapeamento e o diff
  legado-vs-Django trivial de auditar, mas só funciona para um único tenant: um segundo espelhamento
  colidiria de PK, o que contraria o desenho multi-cooperativa de schema compartilhado
  ([ADR 0001](../../decisions/0001-multi-tenancy-schema-compartilhado.md)).
- **Upsert por chave natural** — não-destrutivo e preservaria edições feitas nas grades, mas exigiria
  adicionar `UniqueConstraint` aos modelos Django (hoje só `Cenario` tem uma, em `cooperativa`+`nome`) e
  decidir o destino de linhas órfãs. Escopo maior, e mudança de modelo de produção a serviço de uma
  ferramenta de desenvolvimento.

**Consequência aceita e explícita:** edições feitas nas grades são perdidas sem aviso na próxima
execução, além da confirmação interativa. Esta é a razão das guardas da §5.

### 4. Remapeamento de IDs

`escrever` mantém três dicts `legado_id → django_id`, para cenários, fábricas e armazéns, populados à
medida que insere em ordem de dependência: Cenário → Fábrica/Armazém → Rota → Previsões → Safra.

O ponto frágil é `SafraUnidade.entidade_id`: um inteiro solto, **não uma FK**
(`apps/simulacao/models.py`), apontando para uma fábrica ou um armazém conforme `entidade_tipo`. Nada no
banco impediria que apontasse para o vazio depois do remapeamento. É por isso que ele ganha teste
dedicado (§6). A convenção de valor de `entidade_tipo` é a que a view já assume (`safras_grid`):
`'Armazém'` identifica armazém, qualquer outro valor identifica fábrica.

### 5. Interface e guardas

```
python manage.py espelhar_legado [--cooperativa-slug comigo] [--usuario teste] [--yes]
```

- Levanta `CommandError` se `settings.DEBUG` for falso — é ferramenta de desenvolvimento, e a operação
  é destrutiva.
- Sem `--yes`, imprime o tenant alvo e as contagens que serão **apagadas**, e pede confirmação.
- `--cooperativa-slug` (default `comigo`) cria ou reusa o tenant. O tenant `Cooperativa Teste`
  pré-existente fica livre e vazio, útil como prova de isolamento entre cooperativas.
- `--usuario` (opcional) repointa um usuário **já existente** para o tenant espelhado. Não cria usuário
  nem manipula senha; isso está fora do escopo de uma ferramenta de dados.

Toda a escrita roda dentro de um `transaction.atomic()`: ou o tenant inteiro é substituído, ou nada é.

### 6. Testes

`apps/simulacao/tests/test_legado.py`, TDD (red → green) como o resto do projeto, cobrindo `escrever`:

1. **Remapeamento das safras** — `entidade_id` aponta para a fábrica/armazém Django correta conforme
   `entidade_tipo`, e nunca para um ID do legado.
2. **Idempotência** — duas execuções seguidas produzem as mesmas contagens e nenhuma duplicata.
3. **Atribuição de tenant** — toda linha escrita tem o `cooperativa_id` do tenant alvo.
4. **Integridade referencial** — cada rota aponta para fábrica e armazém do mesmo cenário.
5. **Isolamento** — espelhar sobre um tenant não toca nas linhas de um tenant vizinho.

O comando roda fora de request, sem contextvar de tenant definida, então acessa os models via
`all_cooperativas` e não `objects` — conforme o
[ADR 0006](../../decisions/0006-engine-services-usam-all-cooperativas.md).

## Verificação

Além da suíte, a etapa só se considera concluída após verificação manual: rodar o comando contra o banco
`comigo` real e abrir as cinco grades (Fábricas, Armazéns, Rotas, Previsões, Datas de Safra) no browser
com dados de produção carregados. É precisamente a prova que as Tasks 5-9 da fase anterior não têm.

## Decisões em aberto / riscos

- **Nomes de cenário longos ou duplicados.** `Cenario` tem `UniqueConstraint(cooperativa, nome)` e
  `max_length=100`. Os 7 nomes legados são curtos e distintos, então não há conflito hoje — mas o
  espelhamento falharia de forma barulhenta (`IntegrityError`) se isso mudasse, o que é o comportamento
  desejado; não vale código defensivo agora.
- **`full_clean` vs `bulk_create`.** A escrita usa inserção em massa e portanto não roda `full_clean`.
  Aceitável: a fonte é um banco relacional com as mesmas restrições, não entrada de usuário. Caso algum
  campo divirja de tipo entre os schemas, o Postgres rejeita na inserção.
- **A ferramenta não tem migração inversa.** Se o banco Django acumular dados que só existam lá, este
  comando os destrói. Enquanto o Django não for fonte da verdade, isso é aceitável; quando for, a
  ferramenta precisa ser aposentada, não adaptada.
- **Datetimes naive do legado.** `Cenario.data_criacao` é naive no legado e `USE_TZ = True` aqui. O que
  o Django 6 realmente faz nesse caso — verificado no fonte de `DateTimeField.get_prep_value` durante a
  revisão desta fase — é emitir um `RuntimeWarning` e então chamar `make_aware` com o `TIME_ZONE`
  default. Como o default é `America/Sao_Paulo`, que é justamente o fuso em que o app Streamlit gravou
  esses valores, **não há deslocamento de horário**. A conversão explícita em
  `legado._data_criacao_aware` existe para eliminar o warning (a saída de teste impecável é exigência
  do projeto) e para tornar a intenção legível, não para corrigir um bug de fuso. Um planejamento
  anterior desta fase afirmou que o Django trataria o valor como UTC e deslocaria tudo em 3 horas;
  isso é falso e não deve ser repetido.
- **Safra com `entidade_id` órfão.** `SafraUnidade.entidade_id` não é FK, então uma safra pode
  sobreviver à unidade que referencia. `escrever` pula essas linhas em vez de abortar — o mesmo que
  `services.clone_scenario` faz — e as contagens devolvidas refletem as linhas realmente escritas. Um
  `safras` menor que o esperado é o sinal para o operador investigar. Na verificação de 2026-08-24 o
  banco legado tinha zero linhas nessa condição.
