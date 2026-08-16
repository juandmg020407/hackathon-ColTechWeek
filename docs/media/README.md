# Imágenes del README

El [README](../../README.md) cuenta el recorrido completo en cinco etapas, y cada
una lleva su imagen. Copia aquí los archivos con **exactamente** estos nombres:

| Archivo | Etapa | Qué debe mostrar |
|---|---|---|
| `1.jpg` | ① La medición en campo | **Foto real.** El agricultor o el técnico insertando el sensor NPK en el suelo del lote de papa. Es la primera imagen que ve quien abre el proyecto y la única que debe ser fotografía auténtica |
| `2.jpg` | ② Recolección y envío a la nube | La lectura viajando del sensor al teléfono del técnico y de ahí a la nube. Idempotencia (`client_id`), captura offline, importación por Excel |
| `3.jpg` | ③ El sistema le suma el clima | El motor cruzando las seis fuentes externas. **Nómbralas en la imagen** con lo que aporta cada una (ver tabla abajo) |
| `4.jpg` | ④ Sale un mapa y una receta que se entiende | Una composición que reúna el mapa con incertidumbre, la receta **recomendada** y el QR que abre el acta humanizada. Debe quedar claro que la IA explica sobre evidencia y que una persona valida |
| `5.jpg` | ⑤ Aplicación precisa y anticipación | Aplicación por zona y alerta anticipada de riesgo climático estacional (El Niño, sequía, helada, gota tardía). Es la imagen que antes se llamaba `6.jpg` |

## Las seis fuentes para la imagen `3.jpg`

| API | Texto corto para la imagen |
|---|---|
| **IDEAM** · `datos.gov.co` | Estaciones físicas colombianas. La más cercana al lote está a **2,47 km** → el único dato de instrumento |
| **Open-Meteo Forecast** | 16 días de pronóstico horario en la coordenada exacta del lote → helada, sequía y gota tardía |
| **NASA POWER** | 20 años de reanálisis diario del mismo punto → a qué año histórico se parece esta temporada |
| **NOAA CPC · ENSO** | Fase e índice de El Niño / La Niña → escala estacional |
| **Anthropic Claude Sonnet 5** | Redacta en español sobre evidencia. No calcula ni decide |
| **OpenStreetMap** | Mapa base opcional; el mapa de suelo funciona sin él |

Si el espacio aprieta, **IDEAM es la que no puede faltar**: es la autoridad
meteorológica colombiana y la única fuente de observación real; las otras
climáticas son productos de modelo.

## Recomendaciones

- **Comprime cada archivo por debajo de 500 KB.** GitHub sirve el README entero y
  cinco imágenes pesadas lo vuelven lento justo cuando alguien lo abre.
- Ancho útil: **1400–1600 px**. Todas se muestran a ancho completo, así que un
  formato horizontal consistente (16:9 o 3:2) hace que el README se lea parejo.
- Si alguna persona es identificable, confirma que dio permiso para publicar la
  imagen. El proyecto declara consentimiento explícito en los datos; las fotos no
  pueden ser la excepción.
- **Cuidado con lo que prometen las imágenes.** El sistema modela helada, sequía
  y gota tardía, más el contexto ENSO. **No modela incendios.** Si `5.jpg` sugiere
  detección de incendios, la imagen estaría afirmando algo que el código no hace
  y el README desmiente explícitamente.
- Los textos alternativos ya están escritos en el README. Si cambias lo que
  muestra una imagen, actualiza también su `alt`.

Mientras los archivos no existan, GitHub mostrará el texto alternativo en lugar
de la imagen.
