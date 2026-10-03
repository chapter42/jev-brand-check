import asyncio
import os

import streamlit as st
from typesafe_sdk import AsyncTypeSafeClient, TypeSafeAuthenticationError

from brand_check import (
    annotate,
    build_pattern,
    judge_rows,
    parse_spellings,
    read_csv,
    summarize,
    to_csv,
)

PREVIEW_ROWS = 5

st.set_page_config(page_title="Jev merkcheck", page_icon="🔎", layout="wide")


def pct(part, total):
    return f"{part / total:.0%}".replace(".", ",") if total else "–"


async def run_jev(key, rows, brand, pattern, column, concurrency, on_progress):
    async with AsyncTypeSafeClient(api_key=key) as client:
        return await judge_rows(client, rows, brand, pattern, column, concurrency, on_progress)


st.title("Jev merkcheck")
st.write(
    "Controleer in een CSV met prompt-resultaten of een merk genoemd en aanbevolen wordt. "
    "Antwoorden waarin het merk niet voorkomt, worden lokaal overgeslagen en niet naar TypeSafe gestuurd."
)

with st.sidebar:
    st.header("TypeSafe API-key")
    key = st.text_input(
        "API-key",
        type="password",
        help="Maak een key aan op console.typesafe.ai. Hij wordt alleen in deze sessie gebruikt en nergens opgeslagen.",
    ).strip()
    # Local convenience only: the environment key is never sent to the browser.
    if not key and os.environ.get("TYPESAFE_API_KEY"):
        key = os.environ["TYPESAFE_API_KEY"]
        st.caption("Leeg gelaten: de key uit `TYPESAFE_API_KEY` op deze machine wordt gebruikt.")

if not key:
    st.info("Vul links je TypeSafe API-key in om te beginnen. Een key maak je aan op console.typesafe.ai.")
    st.stop()

upload = st.file_uploader("CSV met prompt-resultaten", type=["csv", "txt"])
if not upload:
    st.stop()

columns, rows, delimiter = read_csv(upload.getvalue())
if not rows:
    st.error("De CSV bevat geen datarijen.")
    st.stop()

st.subheader("Voorbeeld")
row_count = f"{len(rows):,}".replace(",", ".")
st.caption(f"{row_count} rijen, {len(columns)} kolommen. Dit zijn de eerste {min(PREVIEW_ROWS, len(rows))}.")
st.dataframe(rows[:PREVIEW_ROWS], width="stretch")

st.subheader("Instellingen")
left, right = st.columns(2)
column = left.selectbox("Welke kolom bevat het prompt-antwoord?", columns, index=len(columns) - 1)
brand_input = right.text_input(
    "Om welk merk gaat het?",
    placeholder="Nova, nova.nl",
    help="Extra schrijfwijzen scheid je met komma's. De eerste naam krijgt Jev te zien.",
)
with st.expander("Geavanceerd"):
    concurrency = st.slider("Gelijktijdige requests naar Jev", 1, 20, 5)

spellings = parse_spellings(brand_input)
pattern = build_pattern(spellings) if spellings else None

if pattern:
    matching = sum(bool(pattern.search(row.get(column) or "")) for row in rows)
    st.info(f"{matching} van de {len(rows)} antwoorden bevatten {', '.join(spellings)} en gaan naar Jev.")

run_key = (upload.file_id, column, tuple(spellings))
if st.button("Start check", type="primary", disabled=not spellings):
    progress = st.progress(0.0, text="Bezig met beoordelen…")

    def on_progress(done, total):
        progress.progress(done / total, text=f"Beoordeeld: {done}/{total}")

    try:
        results = asyncio.run(run_jev(key, rows, spellings[0], pattern, column, concurrency, on_progress))
    except TypeSafeAuthenticationError as error:
        progress.empty()
        st.error(f"Gestopt: TypeSafe accepteert de API-key niet. Er is niets beoordeeld.\n\n`{error}`")
        st.stop()
    progress.empty()
    st.session_state["results"] = (run_key, results)

stored = st.session_state.get("results")
if not stored or stored[0] != run_key:
    st.stop()
results = stored[1]

st.subheader("Resultaat")
# Changing the threshold only re-labels stored probabilities; it doesn't call Jev again.
threshold = st.slider("Drempel: vanaf welke kans telt een antwoord als ja?", 0.05, 0.95, 0.5, 0.05)
summary = summarize(results, threshold)
judged = summary["judged"]

cols = st.columns(4)
cols[0].metric("Naar Jev gestuurd", f"{summary['sent']}/{judged}")
cols[1].metric("Genoemd", f"{summary['mentioned']}/{judged}", pct(summary["mentioned"], judged), delta_color="off")
cols[2].metric("Aanbevolen", f"{summary['recommended']}/{judged}", pct(summary["recommended"], judged), delta_color="off")
cols[3].metric("Twijfelgevallen", summary["unsure"], help="Aanbevelingskans tussen 0,3 en 0,7. Bekijk die met de hand.")
if summary["errors"]:
    st.warning(f"{summary['errors']} rijen niet beoordeeld (leeg antwoord of fout), zie kolom `jev_error`.")

annotated = annotate(rows, results, threshold)
st.dataframe(annotated, width="stretch")
st.download_button(
    "Download resultaat als CSV",
    to_csv(columns, annotated, delimiter),
    file_name=f"{os.path.splitext(upload.name)[0]}_jev.csv",
    mime="text/csv",
)
