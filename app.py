import re
import requests
import pandas as pd
import streamlit as st
import altair as alt


# Weltcup-Punkteschema für Plätze 1–30
FIS_POINTS = {
    1: 100, 2: 80, 3: 60, 4: 50, 5: 45,
    6: 40, 7: 36, 8: 32, 9: 29, 10: 26,
    11: 24, 12: 22, 13: 20, 14: 18, 15: 16,
    16: 15, 17: 14, 18: 13, 19: 12, 20: 11,
    21: 10, 22: 9, 23: 8, 24: 7, 25: 6,
    26: 5, 27: 4, 28: 3, 29: 2, 30: 1,
}

API_TEMPLATE = "https://afeeds.orf.at/alpine-api/api/sportevents/{event_id}?detailtype=end"


# -------------------- Helper-Funktionen --------------------


def extract_event_id_from_url(url: str) -> str:
    """
    Extrahiert die Event-ID aus einer ORF-URL, z.B.:
        https://sport.orf.at/skialpin/#/event/11986
        https://afeeds.orf.at/alpine-api/api/sportevents/11986?detailtype=end
    """
    m = re.search(r"(?:/event/|/sportevents/)(\d+)", url)
    if not m:
        raise ValueError("Konnte keine Event-ID aus der URL lesen.")
    return m.group(1)


def fetch_orf_json(event_id: str) -> dict:
    """
    Ruft die ORF-API für ein Event auf und gibt das JSON zurück.
    """
    url = API_TEMPLATE.format(event_id=event_id)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json,text/plain,*/*",
    }
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _find_result_items(obj):
    """
    Rekursive Suche in einem JSON-Objekt nach Elementen, die wie
    Rennergebnisse aussehen (Rank/Position + Nation).
    Gibt eine Liste von dicts zurück.
    """
    found = []

    if isinstance(obj, dict):
        # Heuristik: Ein dict mit Rank/Position und Nation/Country
        keys = set(obj.keys())
        has_rank = any(k in keys for k in ("rank", "position", "place"))
        has_nation = any(
            k in keys for k in ("nation", "nationShort", "countryCode", "country")
        )

        if has_rank and has_nation:
            found.append(obj)

        # Rekursiv weiter
        for v in obj.values():
            found.extend(_find_result_items(v))

    elif isinstance(obj, list):
        for item in obj:
            found.extend(_find_result_items(item))

    return found


def parse_results_from_json(data: dict) -> pd.DataFrame:
    """
    Nimmt das ORF-JSON (alpine-api) und extrahiert daraus
    Rank, Nation und Name aus data["Results"].
    """

    results = data.get("Results", [])
    rows = []

    for item in results:
        # Platz
        rank_val = item.get("RankingFinal")
        try:
            rank = int(rank_val)
        except (TypeError, ValueError):
            continue

        if not (1 <= rank <= 30):
            # wir interessieren uns nur für Top 30
            continue

        # Nation
        nation = item.get("NationCC3")
        if not nation:
            continue

        # Name
        name = item.get("DisplayName") or (
            (item.get("FirstName") or "") + " " + (item.get("LastName") or "")
        ).strip()

        rows.append(
            {
                "Rank": rank,
                "Nation": nation,
                "Name": name,
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df = df.sort_values("Rank").reset_index(drop=True)
    return df



def compute_points_by_nation(df: pd.DataFrame) -> pd.DataFrame:
    """
    Berechnet Weltcup-Punkte je Nation aus einem DataFrame mit Rank/Nation.
    """
    df = df.copy()
    df["Points"] = df["Rank"].map(FIS_POINTS).fillna(0).astype(int)
    by_nat = (
        df.groupby("Nation", as_index=False)["Points"]
        .sum()
        .sort_values("Points", ascending=False)
    )
    return by_nat


# -------------------- Streamlit UI --------------------


# -------------------- Streamlit UI --------------------

st.title("Ski-Weltcup – Punkte je Nation pro Rennen (ORF-API)")
st.markdown(
    """
    Gib den Link zu einem ORF-Skialpin-Event ein, z.B.  
    <a href="https://sport.orf.at/skialpin/#/termine" target="_blank">https://sport.orf.at/skialpin/#/termine</a>  
    und wähle dort ein Rennen aus.

    Kopiere dann den Event-Link (z.B. `https://sport.orf.at/skialpin/#/event/11986`).
    """,
    unsafe_allow_html=True
)


# Standardwert im Eingabefeld (kannst du jederzeit anpassen)
default_url = "https://sport.orf.at/skialpin/#/termine"

# Formular: Enter im Textfeld löst automatisch Submit aus
with st.form("event_form"):
    user_url = st.text_input("ORF-Event-URL", value=default_url)
    submitted = st.form_submit_button("Punkte je Nation berechnen")

if submitted:
    try:
        event_id = extract_event_id_from_url(user_url)
        with st.spinner(f"Lade ORF-Daten für Event {event_id}..."):
            data = fetch_orf_json(event_id)

        df_results = parse_results_from_json(data)

        if df_results.empty:
            st.error(
                "Es konnten keine gültigen Resultate (Rank + Nation) im ORF-JSON "
                "gefunden werden. Eventuell hat sich die Struktur geändert."
            )
        else:
            st.subheader("Erkannte Läuferinnen (Top 30)")
            st.dataframe(df_results)

            df_nat = compute_points_by_nation(df_results)
            st.subheader("Punkte je Nation")
            st.dataframe(df_nat)

            # --- Balkendiagramm mit Labels ---
            st.subheader("Grafik: Punkte je Nation")

            chart_data = df_nat.sort_values("Points", ascending=False)

            base = alt.Chart(chart_data)

            bars = base.mark_bar().encode(
                x=alt.X("Nation:N", sort=None),
                y=alt.Y("Points:Q"),
                tooltip=["Nation", "Points"],
            )

            labels = base.mark_text(
                dy=-5,
                baseline="bottom",
            ).encode(
                x=alt.X("Nation:N", sort=None),
                y=alt.Y("Points:Q"),
                text="Points:Q",
            )

            chart = (bars + labels).properties(height=400)
            st.altair_chart(chart, use_container_width=True)

    except ValueError as e:
        st.error(f"Fehler in der URL: {e}")
    except requests.RequestException as e:
        st.error(f"Fehler beim Aufruf der ORF-API: {e}")
    except Exception as e:
        st.error(f"Unerwarteter Fehler: {e}")
