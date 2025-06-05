# app.py
# Streamlit-App zum Hochladen und Visualisieren von GeoJSON-Punkten,
# Ziehen von Richtungs­linien, kontinuierlichem Nummerieren
# sowie Export der nummerierten Punkte als GeoJSON.
#
# Fallback: Wenn kein eigenes Dataset hochgeladen wird,
# verwendet die App automatisch "data/DummyDaten.geojson".

import pathlib
import itertools

import streamlit as st
import geopandas as gpd
import pandas as pd
from shapely.geometry import shape, Point
from streamlit_folium import st_folium
import folium
from folium.plugins import Draw

# -------------------------------------------------------------------
# Konfiguration & Standardpfad
# -------------------------------------------------------------------
DEFAULT_FILE = pathlib.Path(__file__).parent / "data" / "defaultDaten.geojson"

st.set_page_config(page_title="GeoJSON-Visualizer", layout="wide")

# -------------------------------------------------------------------
# Titel & Sidebar-Eingaben
# -------------------------------------------------------------------
st.title("GeoJSON-Visualizer mit Nummerierung & Export")

st.sidebar.header("Punktdaten")
hochgeladene_datei = st.sidebar.file_uploader(
    "GeoJSON mit Punkt-Features hochladen",
    type=["geojson", "json"]
)

zoom_level = st.sidebar.slider(
    "Start- & Max-Zoomstufe", min_value=10, max_value=30, value=25, step=1
)

threshold = st.sidebar.slider(
    "Entfernungs­schwelle für Auswahl (Meter)",
    min_value=0.1, max_value=50.0,
    value=1.0, step=0.1
)

# -------------------------------------------------------------------
# Fallback-Logik
# -------------------------------------------------------------------
if hochgeladene_datei is not None:
    datei_zur_verwendung = hochgeladene_datei
    st.sidebar.success("Eigene Datei erkannt – benutze Upload.")
else:
    datei_zur_verwendung = DEFAULT_FILE
    st.sidebar.info("Kein Upload erkannt – benutze defaultDaten.geojson.")

# -------------------------------------------------------------------
# Haupt-App-Logik
# -------------------------------------------------------------------
if datei_zur_verwendung:
    try:
        # GeoJSON einlesen & prüfen
        gdf = gpd.read_file(datei_zur_verwendung)
        if not all(gdf.geometry.geom_type == "Point"):
            st.error("Die GeoJSON muss ausschließlich Punktgeometrien enthalten.")
            st.stop()

        gdf = gdf.reset_index().rename(columns={"index": "orig_index"})
        gdf["lon"] = gdf.geometry.x
        gdf["lat"] = gdf.geometry.y

        st.subheader("Rohdaten – Punktkoordinaten")
        st.dataframe(gdf[["orig_index", "lon", "lat"]])

        # Projektion für metrische Berechnungen
        gdf_proj = (
            gdf[["orig_index", "geometry"]]
            .set_geometry("geometry")
            .to_crs(epsg=3857)
        )

        # Kartenmittelpunkt
        center = [gdf["lat"].mean(), gdf["lon"].mean()]

        # Basiskarte (Satellit)
        m = folium.Map(
            location=center,
            zoom_start=zoom_level,
            tiles=None,
            min_zoom=1,
            max_zoom=zoom_level,
            control_scale=True,
            zoom_control=True,
        )
        folium.TileLayer(
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            attr="Esri",
            name="Satellit",
            overlay=False,
            control=True,
            max_native_zoom=19,
            max_zoom=zoom_level,
        ).add_to(m)

        # Originalpunkte als rote Kreise
        for _, row in gdf.iterrows():
            folium.CircleMarker(
                location=[row.lat, row.lon],
                radius=4,
                color="red",
                fill=True,
                fill_color="red",
                fill_opacity=0.8,
            ).add_to(m)

        # Zeichenwerkzeug für Linien
        Draw(
            export=True,
            filename="linien.geojson",
            draw_options={
                "polyline": True,
                "polygon": False,
                "circle": False,
                "rectangle": False,
                "marker": False,
                "circlemarker": False,
            },
            edit_options={"edit": True},
        ).add_to(m)

        st.subheader("Linien zeichnen, um Nummerier­richtung festzulegen")
        draw_output = st_folium(m, width=800, height=600)

        # ------------------------------------------------------------
        # Gezeichnete Linien verarbeiten
        # ------------------------------------------------------------
        if draw_output and draw_output.get("all_drawings"):
            features = draw_output["all_drawings"]
            n = len(features)
            st.write(f"Du hast **{n}** Linien gezeichnet.")

            ids = list(range(1, n + 1))
            col1, col2 = st.columns(2)
            start = col1.selectbox("Start-Linie", ids)
            stop = col2.selectbox("Stopp-Linie", ids, index=n - 1)

            seq = (
                list(range(start, stop + 1))
                if start <= stop
                else list(range(start, stop - 1, -1))
            )

            # Ergebnis-Karte
            m2 = folium.Map(
                location=center,
                zoom_start=zoom_level,
                tiles=None,
                min_zoom=1,
                max_zoom=zoom_level,
                control_scale=True,
                zoom_control=True,
            )
            folium.TileLayer(
                tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                attr="Esri",
                name="Satellit",
                overlay=False,
                control=True,
                max_native_zoom=19,
                max_zoom=zoom_level,
            ).add_to(m2)

            global_counter = 1
            all_results = []
            farben = itertools.cycle(
                ["red", "blue", "green", "orange", "purple", "brown"]
            )

            for idx in seq:
                feat = features[idx - 1]
                farbe = next(farben)

                # Linie projizieren
                line = shape(feat["geometry"])
                line_proj = (
                    gpd.GeoSeries([line], crs="EPSG:4326")
                    .to_crs(epsg=3857)
                    .iloc[0]
                )

                df = gdf_proj.copy()
                df["dist_on"] = df.geometry.apply(lambda p: line_proj.project(p))
                df["dist_to"] = df.geometry.distance(line_proj)

                sel = df[df["dist_to"] <= threshold].copy()
                if sel.empty:
                    continue

                sel = sel.sort_values("dist_on").reset_index(drop=True)

                # Kontinuierliche Nummern vergeben
                sel["order"] = list(
                    range(global_counter, global_counter + len(sel))
                )
                global_counter += len(sel)

                sel = sel.merge(gdf[["orig_index", "lon", "lat"]], on="orig_index")
                all_results.append(sel[["order", "lon", "lat"]])

                # Linie & Marker darstellen
                folium.GeoJson(
                    feat["geometry"],
                    style_function=lambda x, col=farbe: {"color": col},
                ).add_to(m2)

                for _, r in sel.iterrows():
                    folium.map.Marker(
                        location=[r.lat, r.lon],
                        icon=folium.DivIcon(
                            html=f"<div style='font-size:12px;color:{farbe};'>{r.order}</div>"
                        ),
                    ).add_to(m2)

            # ---------------------------------------------
            # Ergebnisse zeigen & Export anbieten
            # ---------------------------------------------
            if all_results:
                df_out = pd.concat(all_results, ignore_index=True)
                st.subheader("Kontinuierliche Nummerier-Ergebnisse")
                st.dataframe(df_out)

                gdf_out = gpd.GeoDataFrame(
                    df_out,
                    geometry=[Point(xy) for xy in zip(df_out.lon, df_out.lat)],
                    crs="EPSG:4326",
                )
                geojson_str = gdf_out.to_json()

                st.download_button(
                    label="Nummerierte GeoJSON herunterladen",
                    data=geojson_str,
                    file_name="nummerierte_punkte.geojson",
                    mime="application/geo+json",
                )

                st.subheader("Kartenansicht mit Nummerierung")
                st_folium(m2, width=800, height=600)
            else:
                st.info(
                    "Keine Punkte innerhalb des Schwellenwertes für die ausgewählten Linien."
                )

    except Exception as e:
        st.error(f"Fehler beim Verarbeiten der GeoJSON: {e}")

# -----------------------------------------------------------------------------
# Ausführung (lokal):
#     pip install -r requirements.txt
#     streamlit run app.py
# -----------------------------------------------------------------------------
