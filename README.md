# VoxPopuli

> *Vox Populi, Vox Dei* — La voz del pueblo es la voz de Dios

**Motor de análisis electoral que escanea todas las redes sociales para predecir tendencias políticas.**

---

## Qué hace

VoxPopuli busca keywords de candidatos en **7 plataformas simultáneamente** (Instagram, Facebook, Twitter/X, TikTok, Reddit, YouTube, Threads), identifica encuestas con reacciones (likes, corazones, etc.), reconoce rostros con IA para asociar imágenes a cada candidato, y genera un ranking con conclusiones sobre quién lidera la intención de voto.

**Sin login. Sin cookies. Sin APIs pagas. 100% datos públicos.**

## Stack

| Capa | Tecnología |
|------|-----------|
| UI | Streamlit |
| Búsqueda web | DuckDuckGo (`duckduckgo_search`) |
| Instagram directo | `instaloader` |
| Reconocimiento facial | OpenCV LBPH + Haar Cascade |
| Base de datos | SQLite |
| Análisis | Pandas + Plotly |
| Lenguaje | Python 3.10+ |

## Instalación

```bash
git clone https://github.com/anomalyco/voxpopuli.git
cd voxpopuli
pip install -r requirements.txt
```

## Uso

```bash
streamlit run app.py
```

1. Escribí keywords separadas por coma: `milei, kicillof, bullrich, massa`
2. Elegí rango de fechas
3. Clic en **Buscar y Analizar**
4. Revisá el ranking, tendencias y conclusión automática

### Configurar candidatos

Editá `config.py` para agregar, quitar o modificar candidatos:

```python
CANDIDATES = {
    "javier_milei": {
        "name": "Javier Milei",
        "party": "La Libertad Avanza",
        "keywords": ["milei", "javier milei", "presidente milei"],
        "search_terms": ["milei", "#milei", "#javiermilei"],
        "color": "#8B5CF6"
    },
    # ...
}
```

## Estructura

```
voxpopuli/
├── app.py                       # UI Streamlit
├── config.py                    # Candidatos, plataformas, pesos
├── requirements.txt
├── scraper/
│   ├── web_searcher.py          # Búsqueda multi-plataforma vía DuckDuckGo
│   ├── instagram_scraper.py     # Búsqueda directa en Instagram
│   ├── facebook_scraper.py      # Facebook público + fallback DDG
│   └── base.py                  # Rate limiting, headers
├── analyzer/
│   ├── face_matcher.py          # Reconocimiento facial con OpenCV LBPH
│   ├── reaction_analyzer.py     # Ponderación de reacciones
│   └── aggregator.py            # Rankings, tendencias, conclusión
├── database/
│   └── db.py                    # SQLite schema + queries
└── utils/
    └── helpers.py               # Detección de encuestas, parseo
```

## Ponderación de engagement

| Reacción | Peso |
|----------|------|
| ❤️ Me encanta / Love | 1.5x |
| 🫶 Me importa / Care | 1.2x |
| 👍 Me gusta / Like | 1.0x |
| 😮 Me asombra / Wow | 0.9x |
| 😂 Me divierte / Haha | 0.8x |
| 😢 Me entristece / Sad | 0.5x |
| 😡 Me enoja / Angry | 0.3x |

## Limitaciones

- Los datos provienen de búsquedas web públicas. No reflejan el universo completo de cada red social.
- Instagram sin login solo accede a posts de hashtags públicos.
- El reconocimiento facial con Haar Cascade es básico (~70% precisión). Para mayor precisión instalar `dlib` + `face_recognition`.
- Respeta rate-limiting para evitar bloqueos (3-5 segundos entre requests).

## Licencia

MIT
