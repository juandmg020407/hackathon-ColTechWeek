"""
Vuelca el paquete de un lote a mock/ para que el frontend trabaje sin backend.

    python tools/build_mock.py            todos los lotes del catalogo
    python tools/build_mock.py nar-001    uno solo

Antes este script era una copia del pipeline. Ya no: llama al mismo codigo
que sirve el endpoint, asi que el mock y la API no se pueden separar. Una
sola fuente de verdad; si el paquete cambia, el mock cambia con el.

Necesita red la primera vez -clima, estacional y veinte anos de NASA POWER-.
Si alguna fuente no responde, el paquete sale igual con `degradado: true`,
que es exactamente lo que veria el agricultor.
"""

import asyncio
import json
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "backend"))

from app.main import LOTES, _cargar          # noqa: E402
from app.ml import package as pkg            # noqa: E402

SALIDA = RAIZ / "mock"


async def construir(lote_id: str) -> pathlib.Path:
    meta = LOTES[lote_id]
    paquete = await pkg.construir(_cargar(lote_id), meta)
    crudo = paquete.model_dump_json(exclude_none=False)

    destino = SALIDA / f"package-{lote_id}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(crudo, encoding="utf-8")

    bytes_ = len(crudo.encode())
    try:
        import brotli
        comprimido = f"{len(brotli.compress(crudo.encode(), quality=5)) / 1024:.1f} KB"
    except ImportError:
        comprimido = f"~{bytes_ / 1024 / 3.2:.1f} KB estimado"

    riesgos = " · ".join(f"{r.tipo}/{r.severidad}" for r in paquete.riesgos) or "ninguno"
    ajustes = " · ".join(f"{a.nutriente}x{a.factor}" for a in paquete.receta.ajustes) or "ninguno"

    print(f"{lote_id}")
    print(f"  area          {paquete.plot.area_ha} ha, {len(paquete.puntos)} puntos validos, "
          f"{len(paquete.descartados)} descartados")
    print(f"  grilla        {paquete.grid.cols}x{paquete.grid.rows}, "
          f"{sum(paquete.grid.mask)} celdas dentro del lote")
    print(f"  zonas         " + "  ".join(f"{z.id}={z.area_ha}ha" for z in paquete.zonas))
    print(f"  riesgos       {riesgos}")
    print(f"  ajustes       {ajustes}")
    print(f"  receta        {paquete.receta.costo_total_cop:,} COP  "
          f"(ahorro {paquete.receta.ahorro_cop:,})".replace(",", "."))
    if paquete.climatologia:
        print(f"  climatologia  {paquete.climatologia.dias_de_historia} dias, "
              f"{len(paquete.climatologia.anos_analogos)} anos analogos")
    print(f"  degradado     {paquete.degradado}")
    print(f"  peso          {bytes_ / 1024:.1f} KB sin comprimir -> {comprimido} con brotli")
    print(f"  escrito en    {destino.relative_to(RAIZ)}")
    return destino


async def main() -> None:
    pedidos = sys.argv[1:] or list(LOTES)
    for lote_id in pedidos:
        if lote_id not in LOTES:
            print(f"no existe el lote {lote_id}")
            continue
        await construir(lote_id)


if __name__ == "__main__":
    asyncio.run(main())
