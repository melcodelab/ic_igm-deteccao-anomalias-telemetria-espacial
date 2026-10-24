"""
Configurações centralizadas do Copiloto MCP.

Todos os parâmetros mutáveis ficam aqui — nenhum número hardcoded nos módulos.
Para testes, instanciar as funções com valores alternativos sem alterar este arquivo.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Missões suportadas
# ---------------------------------------------------------------------------
MISSIONS: set[str] = {"M1", "M2"}

# Canais de telemetria de cada missão no recorte oficial
CHANNELS: dict[str, list[str]] = {
    "M1": [f"channel_{i}" for i in range(41, 47)],   # 6 canais
    "M2": [f"channel_{i}" for i in range(18, 29)],   # 11 canais
}

# Alias do banco SQLite para cada missão (usado no ATTACH)
DB_ALIAS: dict[str, str] = {"M1": "m1", "M2": "m2"}

# ---------------------------------------------------------------------------
# Temporalidade e cadência
# ---------------------------------------------------------------------------
# Cadência mediana de amostragem por missão (segundos)
CADENCIA_S: dict[str, float] = {"M1": 30.0, "M2": 18.0}

# Janela padrão de análise quando nenhuma é especificada (horas)
JANELA_PADRAO_HORAS: int = 6

# Janela de busca de telecomandos antes do instante de referência (minutos)
DELTA_TC_MINUTOS: int = 30

# ---------------------------------------------------------------------------
# Thresholds estatísticos
# ---------------------------------------------------------------------------
# Desvio normalizado (em MADs) acima do qual o canal é considerado "elevado"
DESVIO_ELEVADO: float = 2.0
# Desvio normalizado acima do qual é "muito_elevado"
DESVIO_MUITO_ELEVADO: float = 4.0

# Canal congelado: mesmo valor repetido por esta quantidade de amostras consecutivas
CANAL_TRAVADO_N_AMOSTRAS: int = 10

# Lacuna: intervalo entre timestamps > FATOR × cadência mediana
LACUNA_FATOR: float = 3.0

# ---------------------------------------------------------------------------
# Anti-leakage
# ---------------------------------------------------------------------------
# Split usado como referência de treino para cada missão
SPLIT_ID_PADRAO: dict[str, str] = {
    "M1": "metade_temporal",
    "M2": "balanceado_m2",
}

# Tamanho mínimo de amostra histórica; abaixo disso R6 exige incerteza declarada
MIN_AMOSTRA_HISTORICO: int = 5

# ---------------------------------------------------------------------------
# Identificação do host/modelo que produziu uma explicação (configurável pelo integrador)
# ---------------------------------------------------------------------------
HOST_MODELO_PADRAO: str = "host-mcp"

# ---------------------------------------------------------------------------
# Caminhos padrão
# ---------------------------------------------------------------------------
# Raiz do projeto (dois levels acima de src/mcp/)
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent

DEFAULT_DB_DIR: Path = PROJECT_ROOT / "data"
DEFAULT_REPORTS_DIR: Path = PROJECT_ROOT / "reports"
RESOURCES_DIR: Path = Path(__file__).resolve().parent / "resources"
