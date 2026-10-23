# Avaliação Contextual da Confiabilidade de Alertas em Telemetria Espacial

> **Iniciação Científica — Geração de Marte**  
> **Linha de Pesquisa:** Estatística, Ciência de Dados e Inteligência Artificial  
> **Estudo Principal:** Benchmark ESA-ADB (*European Space Agency Anomaly Detection Benchmark*)

---

## 🛰️ Visão Geral

Este repositório contém o código, arquitetura de banco de dados e pipeline experimental para avaliar **quando alertas de anomalia em telemetria de satélites merecem confiança**, diferenciando anomalias reais de eventos nominais raros (operações, calibrações) e ruídos de qualidade dos dados.

A arquitetura segue rigorosamente as especificações documentadas em:
- [Arquitetura do Banco de Dados.md](file:///c:/Users/josej/Documents/pesquisa%20geracao%20de%20marte/Arquitetura%20do%20Banco%20de%20Dados.md)
- [Plano de Pesquisa - Confiança em alertas de telemetria espacial.md](file:///c:/Users/josej/Documents/pesquisa%20geracao%20de%20marte/spacecraft-telemetry-anomaly-detection/docs/Projeto%20de%20Pesquisa/Plano%20de%20Pesquisa%20-%20Confian%C3%A7a%20em%20alertas%20de%20telemetria%20espacial.md)
- [MCP.md](file:///c:/Users/josej/Documents/pesquisa%20geracao%20de%20marte/spacecraft-telemetry-anomaly-detection/docs/Projeto%20de%20Pesquisa/MCP.md)

---

## 🗄️ Arquitetura Multi-Banco de Dados (SQLite)

Os dados são organizados em quatro arquivos SQLite complementares em `data/db/`:

```
data/
├── db/
│   ├── esa_catalog.sqlite       ← Metadados unificados, canais, telecomandos, labels auditadas, eventos, janelas e splits (M1 + M2, 3,0 MB)
│   ├── esa_m1.sqlite            ← Telemetria em tabela larga (canais 41–46) e execuções de telecomandos de M1 (15,38M leituras, 1,11 GB)
│   ├── esa_m2.sqlite            ← Telemetria em tabela larga (canais 18–28) e execuções de telecomandos de M2 (7,39M leituras, 935 MB)
│   └── esa_experiments.sqlite   ← Execuções do modelo (runs), normalizações, scores por janela, episódios de alerta e métricas (57 KB)
└── processed/
    ├── M1/metade_temporal/      ← Tensores de janelas (.npy) exportados para treino nominal/validação/teste sem vazamento (M1)
    └── M2/metade_temporal/      ← Tensores de janelas (.npy) exportados para treino nominal/validação/teste sem vazamento (M2)
```

### Por que 4 arquivos?
1. **Segurança do Servidor MCP:** Os dados de telemetria e o catálogo operam em **somente leitura** (`?mode=ro`).
2. **Escrita Concorrente Segura:** O pipeline de machine learning escreve exclusivamente em `esa_experiments.sqlite` com `journal_mode = WAL`.
3. **Desempenho Relacional:** Consultas cruzadas entre telemetria, eventos e telecomandos utilizam `ATTACH DATABASE`.

---

## 🚀 Instalação e Uso

### 1. Configurar o Ambiente

```powershell
# Criar e ativar o ambiente virtual (Python 3.11+)
uv venv .venv
.\.venv\Scripts\Activate.ps1

# Instalar dependências
uv pip install -r requirements.txt
```

### 2. Construir o Ecossistema de Dados Completo

Para carregar os catálogos unificados, processar a telemetria em tabela larga de ambas as missões e exportar os datasets nominais:

```powershell
python -m src.db.build_all --m1-dir "C:\caminho\para\ESA-Mission1" --m2-dir "C:\caminho\para\ESA-Mission2" --export-ml
```

### 3. Rodar os Testes Automatizados (10/10)

```powershell
pytest -v tests/test_database_architecture.py
```

### 4. Executar Verificação de Integridade Isoladamente

```powershell
python -c "from src.db.verify_integrity import run_full_validation; run_full_validation()"
```

---

## 📊 Estatísticas e Validações Consolidadas

| Métrica | Mission 1 (Canais 41–46) | Mission 2 (Canais 18–28) |
|---|---|---|
| **Período de Telemetria** | 2000-01-01 a 2013-12-31 (~14 anos) | 2000-01-01 a 2003-06-30 (~3,5 anos) |
| **Total de Leituras por Canal** | 15.381.169 | 7.387.262 |
| **Linhas em `labels.csv`** | 3.589 auditadas (100% válidas) | 11.167 auditadas (100% válidas) |
| **Eventos Consolidados no Recorte** | 118 (51 Anomaly, 63 Rare Event, 4 Gap) | 622 (19 Anomaly, 603 Rare Event, 0 Gap) |
| **Janelas Contextuais Pareadas** | 708 (1h, 6h e 24h + referências) | 3.732 (1h, 6h e 24h + referências) |
| **Execuções de Telecomandos** | 1.594.722 execuções (698 tipos) | Execuções completas (123 tipos) |
| **Tamanho do Banco de Telemetria** | 1,11 GB | 935 MB |
| **Tensores de Treino Nominal (.npy)** | shape (670.922, 60, 6) | shape (294.945, 60, 11) |