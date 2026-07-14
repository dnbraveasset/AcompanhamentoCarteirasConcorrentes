"""
Utilitários de CNPJ.

O CNPJ é a CHAVE PRINCIPAL de todo o sistema. Por isso ele é sempre tratado
como TEXTO, nunca como número, para não perder zeros à esquerda.

Regras implementadas:
- remover pontos, barras, traços e espaços;
- manter apenas dígitos;
- validar 14 dígitos + dígitos verificadores;
- preservar zeros à esquerda;
- retornar versão limpa e versão formatada;
- descartar falsos positivos (repetições tipo 00000000000000, sequências etc.).
"""
from __future__ import annotations

import re
from typing import Iterable, List, Optional

# Regex para achar CNPJs em texto livre (formatado ou não).
# Aceita 00.000.000/0000-00 e 00000000000000.
CNPJ_REGEX = re.compile(
    r"\b(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})\b"
)

# Falsos positivos óbvios: todos os dígitos iguais.
_CNPJS_INVALIDOS_OBVIOS = {str(d) * 14 for d in range(10)}


def apenas_digitos(valor: Optional[str]) -> str:
    """Remove tudo que não for dígito."""
    if valor is None:
        return ""
    return re.sub(r"\D", "", str(valor))


def _calcular_digito(cnpj_parcial: str, pesos: List[int]) -> int:
    soma = sum(int(d) * p for d, p in zip(cnpj_parcial, pesos))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def validar_cnpj(cnpj: Optional[str]) -> bool:
    """Valida um CNPJ pelos dígitos verificadores.

    Retorna False para nulos, tamanhos errados, repetições e DV inválido.
    """
    num = apenas_digitos(cnpj)
    if len(num) != 14:
        return False
    if num in _CNPJS_INVALIDOS_OBVIOS:
        return False

    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

    dv1 = _calcular_digito(num[:12], pesos1)
    dv2 = _calcular_digito(num[:12] + str(dv1), pesos2)

    return num[12] == str(dv1) and num[13] == str(dv2)


def normalizar_cnpj(cnpj: Optional[str], validar: bool = True) -> Optional[str]:
    """Retorna o CNPJ limpo (14 dígitos, string) ou None.

    Se ``validar`` for True, aplica os dígitos verificadores. Se for False,
    apenas garante 14 dígitos (útil quando quisermos manter possíveis CNPJs
    mesmo com DV divergente, sinalizando depois).
    """
    num = apenas_digitos(cnpj)
    if len(num) != 14:
        return None
    if num in _CNPJS_INVALIDOS_OBVIOS:
        return None
    if validar and not validar_cnpj(num):
        return None
    return num


def formatar_cnpj(cnpj: Optional[str]) -> Optional[str]:
    """Formata como 00.000.000/0000-00. Retorna None se não tiver 14 dígitos."""
    num = apenas_digitos(cnpj)
    if len(num) != 14:
        return None
    return f"{num[:2]}.{num[2:5]}.{num[5:8]}/{num[8:12]}-{num[12:]}"


def extrair_cnpjs(texto: str, validar: bool = True) -> List[str]:
    """Extrai CNPJs (limpos, sem duplicar, preservando ordem) de texto livre."""
    if not texto:
        return []
    vistos: List[str] = []
    for bruto in CNPJ_REGEX.findall(texto):
        limpo = normalizar_cnpj(bruto, validar=validar)
        if limpo and limpo not in vistos:
            vistos.append(limpo)
    return vistos


def deduplicar(cnpjs: Iterable[str]) -> List[str]:
    vistos: List[str] = []
    for c in cnpjs:
        if c and c not in vistos:
            vistos.append(c)
    return vistos
