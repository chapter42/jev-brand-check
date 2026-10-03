# BUILDLOG

## 2026-10-03

**Gebouwd**
- Port van een eerder CLI-script naar een Streamlit-app.
  De logica staat in `brand_check.py`, de interface in `app.py`.
- Voorfilter met een regex op hele woorden en meerdere schrijfwijzen. Alleen
  antwoorden waarin het merk voorkomt, gaan naar Jev (twee Nouls: mentioned en
  recommended).
- De run stopt direct bij een ongeldige API-key (`asyncio.TaskGroup`). Andere fouten
  komen per rij in `jev_error`.
- Een andere drempel rekent de opgeslagen kansen opnieuw door zonder nieuwe Jev-calls.
- 15 pytest-tests met een nep-client (geen API-calls).
- De API-key is een wachtwoordveld in de zijbalk in plaats van een Streamlit-secret,
  zodat de repo publiek kan en elke gebruiker zijn eigen credits gebruikt. Lokaal
  blijft `TYPESAFE_API_KEY` als terugvaloptie.
- Voorbeeldmerken zijn vervangen door fictieve namen (Nova, Orbit, A&B).

**Kapot en opgelost**
- De nep-client in de tests antwoordde zonder te wachten, waardoor het afbreken
  bij een ongeldige key niet testbaar was. Er staat nu een `asyncio.sleep` in,
  net als bij een echte netwerkcall.
- Het onderschrift "8 rijen, 3 kolommen" werd "8 rijen. 3 kolommen" door de
  vervanging van de duizendtallen. Nu wordt alleen het getal opgemaakt.
- `use_container_width` is vervangen door `width="stretch"` (verouderd in Streamlit).

**Volgende stap**
- Deployen op Streamlit Community Cloud (zonder key in de Secrets: gebruikers vullen hun eigen key in).
- De drempel afstemmen op een set rijen die met de hand gelabeld is.
