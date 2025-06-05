# GeoJSON Visualizer Streamlit App

This repo contains a Streamlit app to upload GeoJSON point data, interactively draw direction lines,
perform continuous numbering of nearby points, and export the result.

## Project structure

```
geojson_visualizer/
├── app.py
├── requirements.txt
├── packages.txt
├── .streamlit/
│   └── config.toml
```

## Local development

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy to Streamlit Community Cloud

1. Push this folder to a new GitHub repository.
2. Go to <https://share.streamlit.io> and create a new app.
3. Select your repository, branch, and set **`app.py`** as the main file path.
4. Paste the contents of **packages.txt** into the *Advanced → System packages* box.
5. Click **Deploy**. Build takes a few minutes.

