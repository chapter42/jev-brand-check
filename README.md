# Jev merkcheck

Streamlit-app die in een CSV met prompt-resultaten (bijvoorbeeld antwoorden van
ChatGPT, Gemini of Perplexity) controleert of een merk wordt genoemd en of het
wordt aanbevolen. Het oordeel komt van Jev, het System One-model van
[TypeSafe](https://docs.typesafe.ai/). Jev geeft per vraag een kans terug in plaats
van een tekst.

## Lokaal draaien

Python 3.11 of nieuwer.

```bash
pip install -r requirements.txt
streamlit run app.py            # opent op localhost:8501
```

### API-key

Elke gebruiker vult zijn eigen TypeSafe API-key in, in het wachtwoordveld in de
zijbalk. Een key maak je aan in de [TypeSafe-console](https://console.typesafe.ai/).
De key wordt alleen voor die sessie gebruikt en nergens opgeslagen. De checks
lopen dus op de credits van degene die de key invult.

Lokaal kun je het veld leeg laten als de omgevingsvariabele `TYPESAFE_API_KEY` is
gezet. De app gebruikt dan die key, zonder hem naar de browser te sturen:

```bash
echo 'export TYPESAFE_API_KEY="jouw-key"' >> ~/.zshrc   # Linux vaak ~/.bashrc
source ~/.zshrc
```

Op Windows (PowerShell): `setx TYPESAFE_API_KEY "jouw-key"` en daarna een nieuw
venster openen.

## Deployen op Streamlit Community Cloud

1. Ga naar [share.streamlit.io](https://share.streamlit.io) en kies **Create app**,
   daarna **Deploy a public app from GitHub**.
2. Kies deze repo, branch `main` en main file `app.py`.
3. Kies onder **Advanced settings** Python 3.11 of nieuwer.
4. Deploy.

Zet **geen** `TYPESAFE_API_KEY` in de Secrets van de app. Streamlit maakt secrets
beschikbaar als omgevingsvariabelen. Dan wordt jouw key de standaard voor iedereen
die het veld leeg laat, en betaal jij voor hun checks.

## Gebruik

1. Upload een CSV. Het scheidingsteken (`,` `;` tab of `|`) wordt automatisch herkend.
2. Bekijk de eerste 5 rijen.
3. Kies de kolom met het prompt-antwoord.
4. Vul het merk in. Extra schrijfwijzen scheid je met komma's, bijvoorbeeld
   `Nova, nova.nl`. De eerste naam krijgt Jev te zien. De app laat direct zien
   hoeveel antwoorden naar Jev gaan.
5. Klik op **Start check**.
6. Bekijk het resultaat, pas eventueel de drempel aan en download de CSV.

De drempel aanpassen kost niets: de app rekent de bestaande kansen opnieuw door
zonder Jev opnieuw te vragen.

## Hoe het oordeel tot stand komt

**Voorfilter (lokaal, gratis).** Eerst zoekt een regex of een van de schrijfwijzen
als heel woord in het antwoord staat. Hoofdletters maken niet uit, en "Nova" vindt
dus niet "innovatie". Staat het merk er niet in, dan gaat de rij niet
naar TypeSafe en telt hij als niet genoemd en niet aanbevolen.

**Jev (TypeSafe, kost credits).** Voor de overige rijen stelt Jev twee ja/nee-vragen:

- **mentioned**: wordt het merk (of een product of dienst ervan) genoemd?
- **recommended**: raadt het antwoord het merk aan? Een neutrale vermelding, een
  ongunstige vergelijking of een afraden telt niet als aanbeveling.

## Output

Alle oorspronkelijke kolommen, plus:

| Kolom | Inhoud |
| - | - |
| `jev_sent` | `yes`, of `no (brand not in text)` als de voorfilter de rij heeft overgeslagen |
| `jev_mentioned_p` | Kans (0–1) dat het merk genoemd wordt; leeg als de rij niet naar Jev ging |
| `jev_recommended_p` | Kans (0–1) dat het merk aanbevolen wordt; leeg als de rij niet naar Jev ging |
| `jev_mentioned` | `yes`/`no` volgens de drempel |
| `jev_recommended` | `yes`/`no` volgens de drempel |
| `jev_error` | `empty answer` of de API-fout; die rijen tellen niet mee in de samenvatting |

Twijfelgevallen zijn rijen met een aanbevelingskans tussen 0,3 en 0,7. Die kun je
het beste met de hand bekijken.

## Foutafhandeling

- **Geen key ingevuld**: de app vraagt om een key en laat nog geen upload toe.
- **Key ongeldig**: de check stopt bij de eerste afwijzing en er wordt niets
  beoordeeld. Dat kost geen credits.
- **Andere fouten** (time-out, rate limit): die rij krijgt de fout in `jev_error`
  en de rest loopt door.

## Let op

- **Schrijfwijzen**: een variant die je niet opgeeft (zoals "Nova Bank" naast
  "NovaBank") vindt de voorfilter niet. Die rij telt dan als niet genoemd.
- **Kosten**: elke rij waarin het merk voorkomt is één Jev-request. Probeer bij een
  grote CSV eerst een kleine steekproef.
- **Data**: de antwoordtekst en de merknaam gaan naar TypeSafe. Bij klantdata moet
  dat akkoord zijn.
- **Drempel**: 0,5 is een startwaarde. Stem de drempel af op een paar rijen die je
  zelf hebt gecontroleerd voordat je cijfers aan een klant rapporteert.

## Ontwikkelen

```bash
pip install -r requirements-dev.txt
pytest tests/ -v                # draait zonder API-calls, met een nep-client
ruff check .
```

- `brand_check.py`: logica (CSV inlezen, voorfilter, Jev-vragen, samenvatting, export)
- `app.py`: Streamlit-interface
