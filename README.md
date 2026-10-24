# Copiloto MCP para Telemetria Espacial

> Servidor [MCP](https://modelcontextprotocol.io) que conecta dados de telemetria das missões ESA-ADB a qualquer cliente compatível — GitHub Copilot, OpenAI Codex, Claude, ou qualquer outro host que fale o protocolo.

## O que é este projeto

O projeto implementa um **copiloto de análise de telemetria espacial** com dados reais do benchmark [ESA Anomaly Detection Benchmark (ESA-ADB)](https://zenodo.org/records/12528696). Ele não é um detector de anomalias — é a camada que **organiza evidências e explica o que está acontecendo** nos dados de telemetria para um operador ou modelo de linguagem.

**Telemetria** são as medições enviadas continuamente pelos instrumentos da nave ao longo do tempo. Cada série de medições é chamada de **canal**. O benchmark ESA-ADB classifica intervalos desses dados como anomalias (comportamento anormal) ou eventos raros nominais (incomum, mas esperado). Nenhum rótulo confirma uma falha física — são anotações do dataset.

O servidor MCP age como ponte: dado um período de tempo e canais de interesse, ele busca os dados no banco SQLite local, calcula estatísticas, compara com o histórico de treino e devolve um pacote estruturado de evidências. O **modelo de linguagem do host** (Copilot, Codex, etc.) usa esse pacote para escrever a explicação em linguagem natural. O projeto inclui também um **verificador** que audita a resposta antes de apresentá-la.

## Como funciona

```text
Você pergunta no chat do Copilot / Codex
        ↓
O modelo chama uma ferramenta MCP (ex: tool_analyze_window)
        ↓
O projeto consulta os bancos SQLite e calcula as estatísticas
        ↓
O modelo escreve a explicação usando as evidências retornadas
        ↓
O modelo envia o texto ao verificador MCP (tool_verify_explanation)
        ↓
O verificador aprova ou devolve as regras que falharam
```

O MCP não acessa nenhum provedor de IA. Ele entrega dados e ferramentas ao host; o modelo já está disponível no aplicativo onde você conversa.

## O que foi implementado

| Módulo | O que faz |
|---|---|
| `src/db/` | Lê os arquivos brutos do ESA-ADB e constrói quatro bancos SQLite. Inclui validação de integridade e exportação de datasets. |
| `src/mcp/` | Servidor FastMCP com 7 ferramentas, 1 recurso (glossário) e 1 prompt (roteiro de explicação). Inclui o verificador de respostas e o módulo de baseline estatístico. |
| `src/replay/` | Modo de avaliação offline: prepara pacotes de evidências para eventos do split de teste e calcula métricas M1–M6 quando respostas são fornecidas. |

### As 7 ferramentas MCP

| Ferramenta | O que faz |
|---|---|
| `tool_analyze_window` | Estatísticas por canal em um intervalo UTC, comparadas com a referência nominal do período de treino (mediana + MAD). Classifica desvios como `nominal`, `elevado` ou `muito_elevado`. |
| `tool_check_data_quality` | Detecta lacunas de tempo, canais congelados (valor repetido por muitas amostras consecutivas) e leituras ausentes. |
| `tool_find_similar_events` | Busca eventos históricos com os mesmos canais afetados. A busca fica restrita ao período de treino/validação — nunca ao teste. |
| `tool_alert_track_record` | Histórico de alertas anteriores registrados no banco de experimentos. |
| `tool_explain_alert` | Monta um pacote completo de evidências: canais, scores (de um detector externo), qualidade, telecomandos recentes e contexto histórico. |
| `tool_verify_explanation` | Audita a resposta escrita pelo host: verifica se cita apenas dados presentes nas evidências, declara incerteza quando necessário, não confirma falhas físicas, e segue o roteiro de cinco partes. |
| `tool_shift_summary` | Resumo estruturado de um turno ou período: leituras, canais em alerta, qualidade, eventos anotados e telecomandos recentes. |

### Referência estatística (baseline)

`tool_analyze_window` compara cada canal com uma referência calculada **apenas sobre o período de treino**, excluindo os intervalos com rótulos de anomalia. A referência usa a **mediana** e o **MAD** (desvio absoluto mediano, multiplicado por 1,4826 para converter à escala de desvio-padrão). Esse cálculo é feito uma vez por missão e mantido em cache durante a sessão. A primeira chamada pode levar alguns segundos; as seguintes são instantâneas.

O resultado (`nominal` / `elevado` / `muito_elevado`) é uma indicação estatística para análise — não um alerta operacional nem um diagnóstico de falha.

---

## Pré-requisitos

- Python 3.11 ou superior
- Os dados brutos do ESA-ADB (obtidos no Zenodo — veja a seção abaixo)

---

## Instalação

```bash
git clone <url-do-repositorio>
cd spacecraft-telemetry-anomaly-detection

python -m venv .venv
source .venv/bin/activate          # Linux / macOS
# .venv\Scripts\Activate.ps1       # Windows PowerShell

pip install -r requirements.txt
```

Nenhuma chave de API é necessária. O modelo de linguagem é fornecido pelo host (Copilot, Codex, etc.).

---

## Obtendo os dados (Zenodo)

Os bancos SQLite e os arquivos de telemetria **não estão no repositório** — eles somam vários gigabytes e o GitHub não os aceita. A pasta `data/` está no `.gitignore` por esse motivo. Cada pessoa precisa baixar os dados e construir os bancos localmente.

### 1. Baixe os dados brutos

Acesse o Zenodo e baixe os arquivos das missões que deseja usar:

**[https://zenodo.org/records/12528696](https://zenodo.org/records/12528696)**

O dataset ESA-ADB inclui duas missões relevantes para este projeto:

| Missão | Identificador interno | Canais usados |
|---|---|---|
| ESA-Mission1 | `M1` | `channel_41` a `channel_46` (6 canais) |
| ESA-Mission2 | `M2` | `channel_18` a `channel_28` (11 canais) |

Após o download, descompacte os arquivos. Você terá diretórios com estrutura parecida com:

```text
ESA-Mission1/
├── channels.csv
├── labels.csv
├── telecommands.csv
└── train/
    └── ...
ESA-Mission2/
└── ...
```

### 2. Construa os bancos SQLite

A partir da raiz do repositório, com o ambiente virtual ativado:

```bash
python -m src.db.build_all \
  --m1-dir /caminho/para/ESA-Mission1 \
  --m2-dir /caminho/para/ESA-Mission2 \
  --db-dir data
```

O script cria os quatro bancos em `data/`:

```text
data/
├── esa_catalog.sqlite       # missões, canais, eventos, rótulos e divisões de dados
├── esa_m1.sqlite            # telemetria e telecomandos da Mission1  (~1,1 GB)
├── esa_m2.sqlite            # telemetria e telecomandos da Mission2  (~0,9 GB)
└── esa_experiments.sqlite   # execuções, alertas e explicações auditadas
```

> **Atenção:** a carga completa de telemetria pode levar vários minutos dependendo do hardware. Para construir apenas o catálogo (sem telemetria), use `--skip-telemetry`.

---

## Exemplos de uso

Os exemplos abaixo usam datas e eventos reais do dataset ESA-ADB. Basta digitar a pergunta no chat do Copilot ou Codex após conectar o servidor.

---

### Analisar um período de telemetria

> "Analise a telemetria da M2 entre 2001-01-01T00:00:00Z e 2001-01-01T06:00:00Z"

> "Como estavam os canais da M1 no dia 2005-03-30? Use um intervalo de seis horas a partir de 2005-03-30T00:00:00Z"

> "Mostra um resumo do turno da M2 entre 2001-07-15T08:00:00Z e 2001-07-15T20:00:00Z"

O modelo chama `tool_analyze_window` ou `tool_shift_summary`. Para cada canal, você recebe a média, mediana, desvio em relação ao histórico de treino e uma classificação (`nominal`, `elevado` ou `muito_elevado`). O resumo de turno inclui também telecomandos e eventos anotados no período.

---

### Verificar qualidade dos dados

> "Houve lacunas ou canais travados na M2 entre 2001-05-01T00:00:00Z e 2001-05-01T12:00:00Z?"

> "Verifica a qualidade dos dados da M1 na semana de 2007-01-15T00:00:00Z a 2007-01-22T00:00:00Z"

O modelo chama `tool_check_data_quality` e lista lacunas de tempo detectadas, canais com valor repetido por muitas amostras consecutivas e leituras ausentes no período.

---

### Explorar um evento anotado no dataset

> "Explica o que aconteceu na M2 durante o evento id_639, que ocorreu em 2000-05-23 entre 16:30 e 17:40 UTC, afetando os canais channel_21, channel_22 e channel_23"

> "Analisa o evento id_167 da M1, que vai de 2000-03-19T06:01:28Z a 2000-03-20T23:13:58Z. Os canais afetados são channel_41, channel_42, channel_43, channel_44, channel_45 e channel_46"

> "Olha o evento id_83 da M1, anomalia entre 2002-05-20T22:22:25Z e 2002-05-21T15:43:55Z"

O modelo chama `tool_explain_alert` para reunir evidências (estatísticas do canal, qualidade, telecomandos recentes e eventos similares históricos) e depois chama `tool_verify_explanation` para auditar a resposta antes de exibi-la.

---

### Buscar eventos similares no histórico

> "Existem eventos históricos da M2 similares ao que aconteceu em 2000-05-23T16:30:00Z? Olha especialmente os canais channel_21 e channel_22"

> "Busca eventos anteriores da M1 próximos ao canal channel_43 a partir de 2002-05-20T22:00:00Z"

O modelo chama `tool_find_similar_events`. A busca fica **restrita ao período de treino e validação** — nunca ao split de teste — para evitar vazamento de dados.

---

### Comparar períodos com e sem evento

> "Compara a telemetria da M2 em 2000-05-23T16:00:00Z a 2000-05-23T18:00:00Z (durante o evento id_639) com um período anterior calmo, por exemplo 2000-05-23T08:00:00Z a 2000-05-23T10:00:00Z"

Peça duas chamadas a `tool_analyze_window` e compare os resultados lado a lado. O modelo pode tabular os canais e destacar quais mudaram de `nominal` para `elevado` ou `muito_elevado`.

---

### Consultas sobre a referência de cada canal

> "Qual o valor de referência nominal do channel_22 na M2? O valor está elevado agora em 2001-08-10T00:00:00Z?"

> "O channel_41 da M1 está fora do padrão no período de 2008-01-01T00:00:00Z a 2008-01-01T12:00:00Z?"

A referência é calculada com mediana e MAD sobre o split de treino. O modelo interpreta o campo `desvio_normalizado_mad` retornado pelas ferramentas.

---

### Resumo rápido para um operador de turno

> "Faz um resumo executivo da M2 para o turno entre 2001-09-01T00:00:00Z e 2001-09-01T08:00:00Z. Tem algum canal em alerta? Houve telecomandos?"

> "Prepara um briefing do estado da M1 no início de 2007, de 2007-01-01T00:00:00Z a 2007-01-01T06:00:00Z"

---

### Dicas ao perguntar

- **Sempre informe a missão** (`M1` ou `M2`) e os dois timestamps em formato ISO 8601 com `Z` no final.
- **Para eventos conhecidos**, passe os canais afetados — o modelo usará isso para montar o pacote de evidências.
- **Timestamps da M1** vão de 2000-01-01 a 2013-12-31. **Timestamps da M2** vão de 2000-01-01 a 2003-06-30.
- Se a resposta vier incompleta ou sem verificação, peça explicitamente: *"Agora verifica a explicação com tool_verify_explanation antes de apresentar"*.

---

## Usando o MCP

Há três formas de usar o servidor, dependendo do cliente:

### Opção A — GitHub Copilot no VS Code (modo Agent)

**1.** Inicie o servidor HTTP em um terminal (deixe rodando):

```bash
.venv/bin/python run_mcp_http.py --sse
# Servidor disponível em http://localhost:8765/sse
```

**2.** O arquivo `.vscode/mcp.json` já está configurado no repositório:

```json
{
  "servers": {
    "spacecraft-telemetry": {
      "type": "sse",
      "url": "http://localhost:8765/sse"
    }
  }
}
```

**3.** Abra o Copilot Chat no modo **Agent** (ícone de agente no painel de chat). O servidor `spacecraft-telemetry` aparecerá na lista de ferramentas disponíveis.

**4.** Experimente perguntar:

> "Analise a telemetria da M2 entre 2001-01-01T00:00:00Z e 2001-01-01T06:00:00Z"

### Opção B — OpenAI Codex (extensão VS Code)

Configure via CLI a partir da raiz do projeto:

```bash
codex mcp add spacecraft-telemetry -- .venv/bin/python -m src.mcp.server
codex mcp list
```

Se o Codex iniciar o processo fora da raiz do projeto, configure o diretório de trabalho em `~/.codex/config.toml`:

```toml
[mcp_servers.spacecraft-telemetry]
command = "/caminho/absoluto/para/o/projeto/.venv/bin/python"
args    = ["-m", "src.mcp.server"]
cwd     = "/caminho/absoluto/para/o/projeto"
enabled = true
```

### Opção C — MCP Inspector (interface web para testes)

Para explorar e testar as ferramentas interativamente sem configurar um cliente:

```bash
npx @modelcontextprotocol/inspector .venv/bin/python -m src.mcp.server
# Abre http://localhost:5173
```

---

## Usando as funções diretamente em Python

As ferramentas também podem ser chamadas sem MCP:

```python
from src.mcp.tools.analyze_window import analyze_window

resultado = analyze_window(
    mission="M2",
    ts_inicio_iso="2001-01-01T00:00:00Z",
    ts_fim_iso="2001-01-01T06:00:00Z",
)
print(resultado["canais_em_alerta"])
```

Para montar um pacote de evidências e verificar uma resposta do host:

```python
from src.mcp.tools.explain_alert import explain_alert
from src.mcp.tools.verify_explanation import verify_host_explanation

pacote = explain_alert(
    mission="M2",
    ts_inicio_iso="2001-01-01T00:00:00Z",
    ts_fim_iso="2001-01-01T00:10:00Z",
    canais=["channel_18", "channel_22"],
    scores={"score_max": 0.91},  # fornecido pelo detector externo
)

texto_do_host = "Texto escrito pelo modelo a partir das evidências."
resultado = verify_host_explanation(pacote["evidencia"], texto_do_host)
print(resultado["ok"], resultado["regras_violadas"])
```

---

## Replay de avaliação

O modo replay avalia a qualidade das explicações geradas pelo host para eventos do split de teste. Ele não chama nenhum modelo — você fornece as respostas geradas externamente.

**Passo 1 — Prepare os pacotes de evidências:**

```bash
python -m src.replay.runner --mission M2 --limit 3
# Grava reports/replay/m2_replay.json e reports/cases.md
```

**Passo 2 — Peça ao host uma resposta para cada `event_id` do JSON e salve em um arquivo:**

```json
{
  "id_do_evento": {
    "resposta": "Resposta produzida pelo host para este caso.",
    "ablation_responses": {},
    "repeticoes": []
  }
}
```

**Passo 3 — Execute o replay com as respostas:**

```bash
python -m src.replay.runner \
  --mission M2 \
  --limit 3 \
  --answers-json respostas.json \
  --host-model codex
```

O replay calcula seis métricas:

| Métrica | O que mede |
|---|---|
| M1 | Frequência das regras do verificador que falharam |
| M2 | Precisão e cobertura dos canais citados em relação aos rótulos |
| M3 | Acerto ao distinguir anomalias de eventos raros nominais |
| M4 | Comparação entre pacotes completos e pacotes com contexto removido (ablação) |
| M5 | Estabilidade textual entre respostas repetidas para a mesma evidência |
| M6 | Acerto por faixa de tamanho do histórico de alertas disponível |

Para gerar variantes de ablação (M4), adicione `--prepare-ablations`. Para M5, inclua múltiplas respostas no campo `repeticoes`.

---

## Estrutura do repositório

```text
src/
├── db/       construção, conexão e validação dos bancos SQLite
├── mcp/      servidor MCP, ferramentas, evidências e verificador
│   ├── tools/        implementação de cada tool
│   └── resources/    glossário e roteiro de explicação
└── replay/   replay offline e cálculo das métricas

data/         bancos SQLite locais — não versionados (.gitignore)
reports/      saídas geradas pelo replay
tests/        testes automatizados
.vscode/      configuração MCP para o GitHub Copilot
```

---

## Limites e avisos

- **Não há detector de anomalias integrado.** `tool_explain_alert` recebe canais e scores fornecidos por um detector externo; este projeto não os produz.
- O replay avalia a camada de **explicação**, não a precisão de um detector.
- Os rótulos do ESA-ADB identificam eventos e canais afetados, mas não confirmam falhas físicas nem revelam os nomes reais dos sensores.
- `tool_alert_track_record` retornará histórico vazio enquanto não houver execuções registradas em `esa_experiments.sqlite`.
- Este é um **protótipo de pesquisa**, não um sistema para operar uma nave. O projeto resume evidências; não envia comandos e não substitui avaliação humana.
