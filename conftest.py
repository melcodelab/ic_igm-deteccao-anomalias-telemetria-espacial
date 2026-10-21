import sys
from pathlib import Path

# Adiciona raiz do projeto ao sys.path para resolução limpa de imports
root = Path(__file__).resolve().parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))
