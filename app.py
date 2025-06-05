# app.py
# A Streamlit app to upload, visualize GeoJSON points with satellite background,
# draw multiple direction lines, perform continuous numbering, and export numbered points as GeoJSON.

import streamlit as st
import geopandas as gpd
import pandas as pd
from shapely.geometry import shape, Point
from streamlit_folium import st_folium
import folium
from folium.plugins import Draw
import itertools

# Title
st.title("GeoJSON Visualizer with Numbering & Export")

# --- Sidebar Inputs ---
st.sidebar.header("Point Data")
uploaded_file = st.sidebar.file_uploader(
    "Upload GeoJSON with Point features",
    type=["geojson", "json"]
)

# Zoom control
zoom_level = st.sidebar.slider(
    "Initial & max zoom level", min_value=10, max_value=30, value=25, step=1
)

# Distance threshold slider
threshold = st.sidebar.slider(
    "Selection distance threshold (meters)",
    min_value=0.1, max_value=50.0,
    value=1.0, step=0.1
)

# Main app logic
if uploaded_file:
    try:
        # Read and validate points
        gdf = gpd.read_file(uploaded_file)
        if not all(gdf.geometry.geom_type == 'Point'):
            st.error("Uploaded GeoJSON must contain only Point geometries.")
            st.stop()

        # Reset index, compute lon/lat
        gdf = gdf.reset_index().rename(columns={'index': 'orig_index'})
        gdf['lon'] = gdf.geometry.x
        gdf['lat'] = gdf.geometry.y

        # Display raw points
        st.subheader("Raw Point Coordinates")
        st.dataframe(gdf[['orig_index', 'lon', 'lat']])

        # Prepare projected GeoDataFrame for metric distance computations
        gdf_proj = gdf[['orig_index', 'geometry']].set_geometry('geometry').to_crs(epsg=3857)

        # Compute map center
        center = [gdf['lat'].mean(), gdf['lon'].mean()]

        # Create base Folium map with satellite tiles
        m = folium.Map(
            location=center,
            zoom_start=zoom_level,
            tiles=None,
            min_zoom=1,
            max_zoom=zoom_level,
            control_scale=True,
            zoom_control=True
        )
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            attr='Esri', name='Satellite', overlay=False, control=True,
            max_native_zoom=19, max_zoom=zoom_level
        ).add_to(m)

        # Plot all points in red on the drawing map
        for _, row in gdf.iterrows():
            folium.CircleMarker(
                location=[row.lat, row.lon],
                radius=4,
                color='red', fill=True, fill_color='red', fill_opacity=0.8
            ).add_to(m)

        # Drawing tool for lines
        draw = Draw(
            export=True, filename='lines.geojson',
            draw_options={
                'polyline': True, 'polygon': False,
                'circle': False, 'rectangle': False,
                'marker': False, 'circlemarker': False
            }, edit_options={'edit': True}
        )
        draw.add_to(m)

        st.subheader("Draw Lines to Define Numbering Direction")
        draw_output = st_folium(m, width=800, height=600)

        # Process drawn lines
        if draw_output and draw_output.get('all_drawings'):
            features = draw_output['all_drawings']
            n = len(features)
            st.write(f"You drew {n} lines.")

            # Select start/stop lines
            ids = list(range(1, n + 1))
            c1, c2 = st.columns(2)
            start = c1.selectbox("Start line", ids)
            stop = c2.selectbox("Stop line", ids, index=n-1)

            # Determine sequence
            seq = list(range(start, stop+1)) if start <= stop else list(range(start, stop-1, -1))

            # Create result map
            m2 = folium.Map(
                location=center, zoom_start=zoom_level,
                tiles=None, min_zoom=1, max_zoom=zoom_level,
                control_scale=True, zoom_control=True
            )
            folium.TileLayer(
                tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
                attr='Esri', name='Satellite', overlay=False, control=True,
                max_native_zoom=19, max_zoom=zoom_level
            ).add_to(m2)

            # Continuous numbering
            global_counter = 1
            all_results = []
            colors = itertools.cycle(['red', 'blue', 'green', 'orange', 'purple', 'brown'])

            for idx in seq:
                feat = features[idx - 1]
                color = next(colors)
                # Project line
                line = shape(feat['geometry'])
                line_proj = gpd.GeoSeries([line], crs='EPSG:4326').to_crs(epsg=3857).iloc[0]

                df = gdf_proj.copy()
                df['dist_on'] = df.geometry.apply(lambda p: line_proj.project(p))
                df['dist_to'] = df.geometry.distance(line_proj)

                sel = df[df['dist_to'] <= threshold].copy()
                if sel.empty:
                    continue
                sel = sel.sort_values('dist_on').reset_index(drop=True)

                # Assign continuous order
                sel['order'] = list(range(global_counter, global_counter + len(sel)))
                global_counter += len(sel)

                # Merge back lon/lat
                sel = sel.merge(gdf[['orig_index', 'lon', 'lat']], on='orig_index')
                all_results.append(sel[['order', 'lon', 'lat']])

                # Draw line and markers
                folium.GeoJson(
                    feat['geometry'], style_function=lambda x, col=color: {'color': col}
                ).add_to(m2)
                for _, r in sel.iterrows():
                    folium.map.Marker(
                        location=[r.lat, r.lon],
                        icon=folium.DivIcon(html=f"<div style='font-size:12px;color:{color};'>{r.order}</div>")
                    ).add_to(m2)

            # Display results and export
            if all_results:
                df_out = pd.concat(all_results, ignore_index=True)
                st.subheader("Continuous Numbering Results")
                st.dataframe(df_out)

                # Build GeoDataFrame for export
                gdf_out = gpd.GeoDataFrame(
                    df_out,
                    geometry=[Point(xy) for xy in zip(df_out.lon, df_out.lat)],
                    crs="EPSG:4326"
                )
                geojson_str = gdf_out.to_json()
                st.download_button(
                    label="Download Numbered GeoJSON",
                    data=geojson_str,
                    file_name="numbered_points.geojson",
                    mime="application/geo+json"
                )

                st.subheader("Map View with Numbering")
                st_folium(m2, width=800, height=600)
            else:
                st.info("No points within threshold for selected lines.")

    except Exception as e:
        st.error(f"Error processing GeoJSON: {e}")

# To run:
# pip install streamlit geopandas pandas shapely folium streamlit-folium
# streamlit run app.py
