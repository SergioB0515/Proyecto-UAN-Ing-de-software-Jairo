"""Reajuste fiscal de activos fijos (arts. 70 y 73 ET). Tabla por año gravable.

AG 2025: Decreto 0449 de 2026 (DUR 1625 arts. 1.2.1.17.20 y 1.2.1.17.21).
Si un valor difiere del decreto, prevalece el decreto.
"""

from decimal import Decimal
from typing import Dict, Optional

FUENTE = {
    2025: "Decreto 0449 del 27 de abril de 2026 (art. 1.2.1.17.21 DUR 1625 de 2016)",
}

# Art. 70: porcentaje de reajuste.
REAJUSTE_ART_70 = {2025: Decimal("0.0581")}

# Art. 73, AG 2025: año de adquisición -> (urbano, rural agropecuario, rural).
# 1955 incluye años anteriores.
_TABLA_2025 = """
1955 36085.10 34963.67 35631.92
1956 35363.86 34264.84 34919.74
1957 32744.71 31727.09 32333.48
1958 27626.91 26768.34 27279.95
1959 25257.62 24472.68 24940.42
1960 23574.13 22841.51 23278.07
1961 21981.02 21297.91 21704.97
1962 20800.81 20154.38 20539.58
1963 19429.21 18825.40 19185.21
1964 14857.22 14395.49 14670.63
1965 13600.80 13178.13 13429.99
1966 11865.93 11497.16 11716.90
1967 10462.43 10137.28 10331.03
1968 9714.61 9412.70 9592.60
1969 9113.87 8830.63 8999.41
1970 8380.22 8119.79 8274.98
1971 7823.78 7580.64 7725.53
1972 6934.19 6718.70 6847.11
1973 6097.77 5908.26 6021.19
1974 4981.35 4826.54 4918.79
1975 3981.89 3858.14 3931.88
1976 3386.47 3281.22 3343.94
1977 2698.90 2615.02 2665.00
1978 2117.65 2051.84 2091.05
1979 1768.55 1713.59 1746.34
1980 1398.18 1354.73 1380.62
1981 1121.73 1086.87 1107.65
1982 893.13 865.38 881.92
1983 717.70 695.39 708.68
1984 616.69 597.52 608.94
1985 535.17 518.54 528.45
1986 443.02 429.25 437.46
1987 375.68 364.01 370.97
1988 283.53 274.72 279.97
1989 176.77 171.27 174.55
1990 122.25 118.45 120.71
1991 85.19 82.54 84.12
1992 63.81 61.83 63.01
1993 45.35 43.94 44.78
1994 32.98 31.96 32.57
1995 23.50 22.77 23.20
1996 17.37 16.83 17.15
1997 14.41 13.97 14.23
1998 11.07 10.73 10.93
1999 9.23 8.94 9.11
2000 9.16 8.88 9.05
2001 8.86 8.59 8.75
2002 8.19 7.94 8.09
2003 7.35 7.12 7.26
2004 6.92 6.70 6.83
2005 6.50 6.29 6.41
2006 6.15 5.96 6.07
2007 4.67 4.53 4.62
2008 4.16 4.03 4.11
2009 3.43 3.32 3.38
2010 3.12 3.02 3.08
2011 2.86 2.77 2.82
2012 2.39 2.32 2.36
2013 2.05 1.99 2.03
2014 1.81 1.76 1.79
2015 1.68 1.63 1.66
2016 1.60 1.55 1.58
2017 1.52 1.48 1.50
2018 1.41 1.36 1.39
2019 1.30 1.26 1.28
2020 1.22 1.18 1.21
2021 1.16 1.12 1.14
2022 1.12 1.09 1.11
2023 1.09 1.06 1.08
2024 1.05 1.03 1.05
"""

TIPOS_INMUEBLE = ("URBANO", "RURAL_AGROPECUARIO", "RURAL")


def _cargar(texto: str) -> Dict[str, Dict[int, Decimal]]:
    tabla: Dict[str, Dict[int, Decimal]] = {t: {} for t in TIPOS_INMUEBLE}
    for linea in texto.strip().splitlines():
        anio, *valores = linea.split()
        for tipo, valor in zip(TIPOS_INMUEBLE, valores):
            tabla[tipo][int(anio)] = Decimal(valor)
    return tabla


REAJUSTE_ART_73 = {2025: _cargar(_TABLA_2025)}


def factor_art_73(anio_gravable: int, tipo: str, anio_adquisicion: int) -> Optional[Decimal]:
    """Factor del art. 73, o None sin tabla. Adquirido en el mismo año: 1."""
    tabla = REAJUSTE_ART_73.get(anio_gravable)
    if tabla is None:
        return None
    if anio_adquisicion >= anio_gravable:
        return Decimal("1")
    return tabla[tipo].get(max(anio_adquisicion, 1955))
