#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import streamlit as st
import pandas as pd
import numpy as np
import time
import requests
from math import radians, sin, cos, atan2, sqrt
import pydeck as pdk
from datetime import datetime, timedelta

st.set_page_config(page_title="Localizador e Rotas de Clientes", layout="wide")

ORS_KEY = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjI5ZTlmZjk3ZTg4MzZjZGM1MDc3ZjBlMjNjOWMyYWU5YjM4ZTNhNzFjYTU4YzYxYjRhM2FmNjY0IiwiaCI6Im11cm11cjY0In0="
OPENCAGE_KEY = "480d28fce0a04bd4839c8cc832201807"

# ----------------------------------------------------------------------------- 
# Polígonos das supervisões (cores estilo Google Maps)
# -----------------------------------------------------------------------------
poligono_sup1_verde = [...]
poligono_sup2_azul = [...]
poligono_sup3_amarelo = [...]

dados_zonas = [
    {"nome": "Zona Leste/Litoral - Supervisor 1", "polygon": poligono_sup1_verde, "cor_preenchimento": [0, 220, 0, 45], "cor_borda": [0, 200, 0, 150]},
    {"nome": "Zona Sul/Sudeste - Supervisor 2", "polygon": poligono_sup2_azul, "cor_preenchimento": [0, 150, 255, 45], "cor_borda": [0, 100, 255, 150]},
    {"nome": "Zona Oeste/Sudoeste - Supervisor 3", "polygon": poligono_sup3_amarelo, "cor_preenchimento": [235, 220, 0, 50], "cor_borda": [200, 180, 0, 150]}
]
df_zonas = pd.DataFrame(dados_zonas)

# ----------------------------------------------------------------------------- 
# Supervisores por bairro
# -----------------------------------------------------------------------------
BAIRROS_SUPERVISORES = { ... }  # mantém igual ao seu código

def identificar_supervisor(endereco):
    if pd.isna(endereco):
        return "Não Identificado"
    endereco_lower = str(endereco).lower()
    for bairro, supervisor in BAIRROS_SUPERVISORES.items():
        if bairro in endereco_lower:
            return supervisor
    return "Outra Região"

def obter_cor_supervisor(supervisor, em_apoio=False):
    if em_apoio:
        return [255, 140, 0, 255]
    if supervisor == "Supervisor 1": return [0, 180, 0, 230]
    if supervisor == "Supervisor 2": return [0, 100, 240, 230]
    if supervisor == "Supervisor 3": return [210, 180, 0, 240]
    return [128, 128, 128, 150]

# ----------------------------------------------------------------------------- 
# Funções matemáticas
# -----------------------------------------------------------------------------
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = radians(lat1), radians(lat2)
    dphi, dlambda = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dphi/2)**2 + cos(p1)*cos(p2)*sin(dlambda/2)**2
    return 2*R*atan2(sqrt(a), sqrt(1-a))

def nearest_neighbor_route(start_lat, start_lon, points):
    unvisited = points.copy()
    route = [{"lat": start_lat, "lon": start_lon, "name": "Centro de Distribuição"}]
    current_lat, current_lon = start_lat, start_lon
    while unvisited:
        distances = [(idx, haversine(current_lat, current_lon, p["lat"], p["lon"])) for idx, p in enumerate(unvisited)]
        distances = [d for d in distances if not np.isnan(d[1])]
        if not distances: break
        next_idx = min(distances, key=lambda x: x[1])[0]
        next_point = unvisited.pop(next_idx)
        route.append(next_point)
        current_lat, current_lon = next_point["lat"], next_point["lon"]
    return route

def verificar_visita_no_dia(row, data_alvo):
    try:
        data_ini = pd.to_datetime(row["Data inicial"], dayfirst=True).date()
        freq = int(row["Frequencia"])
        data_alvo_dt = pd.to_datetime(data_alvo).date()
    except Exception:
        return False
    if data_alvo_dt < data_ini: return False
    diferenca_dias = (data_alvo_dt - data_ini).days
    return (diferenca_dias % freq) == 0

# ----------------------------------------------------------------------------- 
# Geocodificação com OpenCage
# -----------------------------------------------------------------------------
def get_coords(address):
    url = f"https://api.opencagedata.com/geocode/v1/json?q={address}&key={OPENCAGE_KEY}&language=pt&countrycode=br&limit=1&no_annotations=1"
    response = requests.get(url).json()
    if response.get('results'):
        coords = response['results'][0]['geometry']
        lat, lon = coords['lat'], coords['lng']
        return lat, lon
    else:
        return None, None

# ----------------------------------------------------------------------------- 
# Sidebar
# -----------------------------------------------------------------------------
st.sidebar.header("📍 Centro de distribuição")
cd_endereco = st.sidebar.text_input("Endereço do CD", "Travessa Francisco Marrocos Portela, Maracanaú - CE")

st.sidebar.header("⚙️ Limites de Capacidade Diária")
cap_max = st.sidebar.number_input("Qtd Máxima de visitas por Supervisor/Dia", min_value=1, max_value=50, value=5)

st.sidebar.header("🔍 Consulta do Operador")
amanha_padrao = datetime(2026, 7, 14).date()
data_consulta = st.sidebar.date_input("Consultar visitas para o dia:", amanha_padrao)

st.sidebar.header("📂 Importar clientes (.xlsx)")
arquivo = st.sidebar.file_uploader("Selecione o arquivo Excel", type=["xlsx"])

# ----------------------------------------------------------------------------- 
# Corpo principal
# -----------------------------------------------------------------------------
st.title("📍 Roteirizador com Supervisão Dinâmica")

cd_lat, cd_lon = (None, None)
if cd_endereco:
    cd_lat, cd_lon = get_coords(cd_endereco)

if arquivo:
    df = pd.read_excel(arquivo)
    df.columns = [c.strip() for c in df.columns]

    colunas_obrigatorias = ["Cliente_ID", "Cliente", "Endereco", "Data inicial", "Frequencia"]
    colunas_faltantes = [c for c in colunas_obrigatorias if c not in df.columns]
    if colunas_faltantes:
        st.error(f"Arquivo inválido. Faltam: {', '.join(colunas_faltantes)}")
        st.stop()

    coords = []
    for _, row in df.iterrows():
        addr = str(row.get("Endereco", "")).strip()
        lat, lon = get_coords(addr)
        coords.append((lat, lon) if lat and lon else (np.nan, np.nan))
    df["Latitude"], df["Longitude"] = zip(*coords)

    df["Supervisor_Original"] = df["Endereco"].apply(identificar_supervisor)
    df["Visita_Hoje"] = df.apply(lambda row: verificar_visita_no_dia(row, data_consulta), axis=1)
    df_dia = df[df["Visita_Hoje"] == True].copy()

    if df_dia.empty:
        st.warning(f"Nenhuma visita programada para {data_consulta.strftime('%d/%m/%Y')}.")
    else:
        # lógica de transbordo igual ao seu código...
        # ...

        # Mapa com pinos estilo Google Maps
        if cd_lat and cd_lon:
            pontos_mapa = [
                {
                    "lat": r["Latitude"], "lon": r["Longitude"],
                    "name": f"Cliente: {r['Cliente']}\nEquipe: {r['Supervisor_Original']}",
                    "icon_data": {
                        "url": "https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-blue.png",
                        "width": 128, "height": 128, "anchorY": 128
                    }
                }
                for _, r in df_dia.iterrows() if not pd.isna(r["Latitude"])
            ]

            rota = nearest_neighbor_route(cd_lat, cd_lon, points=pontos_mapa)
            path_data = [{"path": [[p["lon"], p["lat"]] for p in rota], "name": "Rota"}]

            layer_poligonos = pdk.Layer(
                "PolygonLayer",
                data=df_zonas,
                get_polygon="polygon",
                get_fill_color="cor_preenchimento",
                get_line_color="cor_borda",
                get_line_width=2,
                pickable=True
            )

            icon_layer = pdk.Layer(
                "IconLayer",
                data=pontos_mapa,
                get_icon="icon_data",
                get_size=4,
                size_scale=15,
                get_position=["lon", "lat"],
                pickable=True
            )

            path_layer = pdk.Layer(
                "PathLayer",
                data=path_data,
                get_path="path",
                get_width=4,
                get_color=[0, 150, 255, 200],  # Linha azul bem nítida
                width_min_pixels=2
            )

            # Renderização do mapa
            st.pydeck_chart(pdk.Deck(
                map_style="mapbox://styles/mapbox/light-v10",
                layers=[layer_poligonos, icon_layer, path_layer],
                initial_view_state=pdk.ViewState(latitude=-3.75, longitude=-38.53, zoom=11.2),
                tooltip={"text": "{name}"}
            ))

