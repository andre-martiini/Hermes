"""Gera assets/lut/gaspar.cube: tom levemente quente, contraste médio, pretos levantados (LUT 3D 33³).

    PY gerar_lut.py [--quente 0.03] [--contraste 0.25] [--pretos 0.035] [--saturacao 1.04]

Os números são os botões de ajuste: mexa neles (não no .cube) e gere de novo.
"""
import argparse
from pathlib import Path

import numpy as np

N = 33


def aplicar(rgb: np.ndarray, quente: float, contraste: float, pretos: float, saturacao: float) -> np.ndarray:
    x = pretos + (1 - pretos) * rgb                               # pretos levantados (sem preto chapado)
    s = x * x * (3 - 2 * x)                                       # curva S suave
    x = (1 - contraste) * x + contraste * s                       # contraste médio
    luma = (x * [0.2126, 0.7152, 0.0722]).sum(-1, keepdims=True)
    x = luma + (x - luma) * saturacao
    x = x * [1 + quente, 1 + quente / 3, 1 - quente]              # puxa para o quente
    return np.clip(x, 0, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quente", type=float, default=0.03)
    ap.add_argument("--contraste", type=float, default=0.25)
    ap.add_argument("--pretos", type=float, default=0.035)
    ap.add_argument("--saturacao", type=float, default=1.04)
    a = ap.parse_args()
    v = np.linspace(0, 1, N)
    b, g, r = np.meshgrid(v, v, v, indexing="ij")                 # no .cube o R varia mais rápido
    saida = aplicar(np.stack([r, g, b], -1).reshape(-1, 3), a.quente, a.contraste, a.pretos, a.saturacao)
    arq = Path(__file__).resolve().parent.parent / "assets" / "lut" / "gaspar.cube"
    arq.parent.mkdir(parents=True, exist_ok=True)
    cab = (f'TITLE "Gaspar {a.quente}/{a.contraste}/{a.pretos}/{a.saturacao}"\n'
           f"LUT_3D_SIZE {N}\nDOMAIN_MIN 0 0 0\nDOMAIN_MAX 1 1 1\n")
    arq.write_text(cab + "\n".join(f"{p[0]:.6f} {p[1]:.6f} {p[2]:.6f}" for p in saida) + "\n", encoding="ascii")
    print(arq)


if __name__ == "__main__":
    main()
