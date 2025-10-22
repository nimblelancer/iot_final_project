import json
import numpy as np
import pandas as pd
from shapely.geometry import Polygon
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, html, dcc, Input, Output, State, callback_context
import dash_bootstrap_components as dbc

# ===============================================================
# Helper: generate hex grid clipped by polygon
# ===============================================================
def generate_hex_grid_from_geojson(geojson_data, hex_size=0.001):
    polygon_coords = geojson_data['features'][0]['geometry']['coordinates'][0]
    polygon_shape = Polygon(polygon_coords)

    min_lon, min_lat, max_lon, max_lat = polygon_shape.bounds
    hex_width = 1.5 * hex_size
    hex_height = np.sqrt(3) * hex_size

    lon_points, lat_points = [], []
    col = 0
    lon = min_lon
    while lon < max_lon + hex_width:
        lat = min_lat
        while lat < max_lat + hex_height:
            lat_shift = (0.5 * hex_height) if col % 2 == 1 else 0
            lon_points.append(lon)
            lat_points.append(lat + lat_shift)
            lat += hex_height
        lon += hex_width
        col += 1

    def hexagon_flat(center_lon, center_lat, size):
        angles = np.deg2rad([0, 60, 120, 180, 240, 300, 0])
        return [(center_lon + size * np.cos(a), center_lat + size * np.sin(a)) for a in angles]

    features, centers, temp_values, hum_values, co2_values, battery_values, smoke_values = [], [], [], [], [], [], []
    grid_id = 0
    for center_lon, center_lat in zip(lon_points, lat_points):
        hex_coords = hexagon_flat(center_lon, center_lat, hex_size)
        hex_poly = Polygon(hex_coords)
        inter = hex_poly.intersection(polygon_shape)
        if not inter.is_empty and inter.area / hex_poly.area > 0.5:
            features.append({
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [list(hex_poly.exterior.coords)]},
                "properties": {"grid_id": grid_id, "center_lon": center_lon, "center_lat": center_lat}
            })
            centers.append((center_lat, center_lon))
            temp_values.append(25 + np.random.randn() * 3 + (grid_id % 5))
            hum_values.append(60 + np.random.randn() * 5 - (grid_id % 3))
            co2_values.append(350 + np.random.randn() * 10 + (grid_id % 7) * 5)
            smoke_values.append(np.random.randint(10, 100))
            battery_values.append(np.random.randint(20, 100))
            grid_id += 1

    grid_geojson = {"type": "FeatureCollection", "features": features}
    df_grid = pd.DataFrame({
        "grid_id": list(range(grid_id)),
        "temperature": np.round(temp_values, 2),
        "humidity": np.round(hum_values, 2),
        "co2": np.round(co2_values, 2),
        "smoke": smoke_values,
        "battery": battery_values,
        "center_lat": [c[0] for c in centers],
        "center_lon": [c[1] for c in centers]
    })
    return df_grid, grid_geojson, polygon_coords


# ===============================================================
# App init
# ===============================================================
app = Dash(__name__, 
           title="Forest Fire Monitor - Sơn Trà",
           external_stylesheets=[dbc.themes.CYBORG],
           suppress_callback_exceptions=True)
server = app.server

app.layout = dbc.Container(fluid=True, className="main-container", children=[
    # Header
    dbc.Row([
        dbc.Col([
            html.H1("🌲 Hệ thống giám sát cháy rừng - Sơn Trà", className="app-title")
        ])
    ], className="header-row"),
    
    # Tabs
    dcc.Tabs(id="main-tabs", value="monitor", className="custom-tabs", children=[
        dcc.Tab(label="📊 Giám sát & Phân tích", value="monitor", className="custom-tab"),
        dcc.Tab(label="🌐 Trạng thái mạng", value="network", className="custom-tab"),
    ]),
    
    # Store components
    dcc.Store(id="grid-store"),
    dcc.Store(id="selected-sensor"),
    dcc.Interval(id="refresh-interval", interval=30000, n_intervals=0),
    
    # Tab content
    html.Div(id="tab-content")
])


# ===============================================================
# Callbacks
# ===============================================================
@app.callback(
    Output("tab-content", "children"),
    Input("main-tabs", "value")
)
def render_tab_content(active_tab):
    if active_tab == "monitor":
        return dbc.Container(fluid=True, children=[
            dbc.Row([
                # LEFT COLUMN - MAP
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader([
                            html.Div([
                                html.H5("🗺️ Bản đồ quan sát", className="card-title mb-2"),
                                dbc.ButtonGroup([
                                    dbc.Button("🌡️ Nhiệt độ", id="filter-temp", color="danger", outline=True, size="sm", n_clicks=1),
                                    dbc.Button("💧 Độ ẩm", id="filter-hum", color="info", outline=True, size="sm", n_clicks=0),
                                    dbc.Button("🏭 CO₂", id="filter-co2", color="success", outline=True, size="sm", n_clicks=0),
                                    dbc.Button("💨 Khói", id="filter-smoke", color="warning", outline=True, size="sm", n_clicks=0),
                                    dbc.Button("🔋 Pin", id="filter-battery", color="secondary", outline=True, size="sm", n_clicks=0),
                                ], size="sm", className="filter-buttons")
                            ], className="w-100")
                        ], className="map-card-header"),
                        dbc.CardBody([
                            dcc.Graph(id="map-chart", config={"displayModeBar": False}, style={"height": "70vh"})
                        ], className="p-2")
                    ], className="map-card h-100")
                ], lg=8, md=12, className="mb-3"),
                
                # RIGHT COLUMN - INSIGHTS
                dbc.Col([
                    # Critical Alerts
                    dbc.Card([
                        dbc.CardHeader(html.H6("🚨 Cảnh báo nguy hiểm", className="card-title mb-0")),
                        dbc.CardBody(id="critical-alerts", className="alert-body p-2")
                    ], className="insight-card mb-3"),
                    
                    # Top High Temperature
                    dbc.Card([
                        dbc.CardHeader(html.H6("🔥 Nhiệt độ cao nhất", className="card-title mb-0")),
                        dbc.CardBody(id="top-temperature", className="top-list-body p-2")
                    ], className="insight-card mb-3"),
                    
                    # Low Battery Warning
                    dbc.Card([
                        dbc.CardHeader(html.H6("⚠️ Cảnh báo pin yếu", className="card-title mb-0")),
                        dbc.CardBody(id="low-battery", className="top-list-body p-2")
                    ], className="insight-card mb-3"),
                    
                    # Statistics Summary
                    dbc.Card([
                        dbc.CardHeader(html.H6("📈 Thống kê tổng quan", className="card-title mb-0")),
                        dbc.CardBody(id="statistics-summary", className="p-3")
                    ], className="insight-card")
                ], lg=4, md=12)
            ], className="main-row mb-3"),
            
            # BOTTOM SECTION - SENSOR DETAIL
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader([
                            html.H6("📊 Chi tiết cảm biến", className="card-title d-inline-block mb-0 me-3"),
                            html.Div(id="sensor-info-header", className="d-inline-block sensor-info-header")
                        ]),
                        dbc.CardBody([
                            html.Div(id="sensor-detail-placeholder", children=[
                                html.Div([
                                    html.I(className="fas fa-mouse-pointer", style={"fontSize": "48px", "color": "#6c757d"}),
                                    html.P("Nhấp vào sensor trên bản đồ để xem thông tin chi tiết", 
                                          className="text-muted mt-3")
                                ], className="text-center py-5")
                            ])
                        ], className="p-3")
                    ], className="sensor-detail-card")
                ], width=12)
            ], className="detail-row")
        ])
    else:
        # Network Status Tab (placeholder)
        return dbc.Container(fluid=True, children=[
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.Div([
                                html.H3("🌐 Trạng thái mạng", className="text-center mb-4"),
                                html.P("Phần này sẽ được phát triển bởi thành viên khác trong nhóm", 
                                      className="text-center text-muted"),
                                html.Div([
                                    html.I(className="fas fa-network-wired", style={"fontSize": "64px", "color": "#6c757d"})
                                ], className="text-center my-5")
                            ])
                        ], className="py-5")
                    ], className="mt-3")
                ], width=12)
            ])
        ])


@app.callback(
    Output("map-chart", "figure"),
    Output("grid-store", "data"),
    Input("filter-temp", "n_clicks"),
    Input("filter-hum", "n_clicks"),
    Input("filter-co2", "n_clicks"),
    Input("filter-smoke", "n_clicks"),
    Input("filter-battery", "n_clicks"),
    Input("refresh-interval", "n_intervals")
)
def update_map(temp_clicks, hum_clicks, co2_clicks, smoke_clicks, battery_clicks, n_intervals):
    ctx = callback_context
    if not ctx.triggered:
        filter_by = "temperature"
    else:
        button_id = ctx.triggered[0]["prop_id"].split(".")[0]
        filter_map = {
            "filter-temp": "temperature",
            "filter-hum": "humidity",
            "filter-co2": "co2",
            "filter-smoke": "smoke",
            "filter-battery": "battery"
        }
        filter_by = filter_map.get(button_id, "temperature")
    
    with open("map.geojson", "r", encoding="utf-8") as f:
        geojson_data = json.load(f)
    df_grid, grid_geojson, polygon_coords = generate_hex_grid_from_geojson(geojson_data)

    color_scales = {
        "temperature": "Reds",
        "humidity": "Blues_r", 
        "co2": "YlOrRd",
        "smoke": "Oranges",
        "battery": "RdYlGn"
    }
    
    titles = {
        "temperature": "Nhiệt độ (°C)",
        "humidity": "Độ ẩm (%)",
        "co2": "CO₂ (ppm)",
        "smoke": "Mức khói",
        "battery": "Pin (%)"
    }

    fig = px.choropleth(
        df_grid, geojson=grid_geojson, locations="grid_id", color=filter_by,
        featureidkey="properties.grid_id", 
        color_continuous_scale=color_scales[filter_by],
        labels={filter_by: titles[filter_by]}
    )

    # Build hover data arrays
    hover_data = []
    for _, row in df_grid.iterrows():
        hover_text = (
            f"<b>Sensor #{int(row['grid_id'])}</b><br>" +
            f"🌡️ Nhiệt độ: {row['temperature']:.1f}°C<br>" +
            f"💧 Độ ẩm: {row['humidity']:.1f}%<br>" +
            f"🏭 CO₂: {row['co2']:.0f} ppm<br>" +
            f"💨 Khói: {row['smoke']}<br>" +
            f"🔋 Pin: {row['battery']}%<br>" +
            "<extra></extra>"
        )
        hover_data.append(hover_text)
    
    fig.update_traces(
        marker_line_width=0.5,
        marker_line_color='rgba(255,255,255,0.3)',
        hovertemplate=hover_data,
        customdata=df_grid[["grid_id"]].values
    )
    
    fig.update_geos(
        fitbounds="locations", 
        visible=False, 
        bgcolor="#1a1a1a"
    )
    
    # Add boundary
    fig.add_trace(go.Scattergeo(
        lon=[p[0] for p in polygon_coords], 
        lat=[p[1] for p in polygon_coords],
        mode="lines", 
        line=dict(width=2, color="#00d4ff"),
        name="Ranh giới",
        showlegend=False,
        hoverinfo='skip'
    ))
    
    fig.update_layout(
        paper_bgcolor="#1a1a1a",
        plot_bgcolor="#1a1a1a",
        font_color="white",
        margin=dict(l=0, r=0, t=0, b=0),
        clickmode='event+select',
        coloraxis_colorbar=dict(
            title=titles[filter_by],
            thickness=15,
            len=0.7
        )
    )
    
    return fig, df_grid.to_json(orient="split")


@app.callback(
    Output("critical-alerts", "children"),
    Output("top-temperature", "children"),
    Output("low-battery", "children"),
    Output("statistics-summary", "children"),
    Input("grid-store", "data")
)
def update_insights(grid_json):
    if not grid_json:
        return "Đang tải...", "Đang tải...", "Đang tải...", "Đang tải..."
    
    df = pd.read_json(grid_json, orient="split")
    
    # Critical Alerts
    critical = []
    high_temp = df[df["temperature"] > 32]
    high_co2 = df[df["co2"] > 400]
    high_smoke = df[df["smoke"] > 70]
    
    if len(high_temp) > 0:
        top_sensor = high_temp.nlargest(1, "temperature").iloc[0]
        critical.append(
            dbc.Alert([
                html.Strong(f"🔥 {len(high_temp)} sensor nhiệt độ cao (>32°C)"),
                html.Br(),
                html.Small(f"Cao nhất: Sensor #{int(top_sensor['grid_id'])} - {top_sensor['temperature']:.1f}°C")
            ], color="danger", className="mb-2 py-2")
        )
    
    if len(high_co2) > 0:
        top_sensor = high_co2.nlargest(1, "co2").iloc[0]
        critical.append(
            dbc.Alert([
                html.Strong(f"🏭 {len(high_co2)} sensor CO₂ cao (>400ppm)"),
                html.Br(),
                html.Small(f"Cao nhất: Sensor #{int(top_sensor['grid_id'])} - {top_sensor['co2']:.0f}ppm")
            ], color="warning", className="mb-2 py-2")
        )
    
    if len(high_smoke) > 0:
        top_sensor = high_smoke.nlargest(1, "smoke").iloc[0]
        critical.append(
            dbc.Alert([
                html.Strong(f"💨 {len(high_smoke)} sensor phát hiện khói (>70)"),
                html.Br(),
                html.Small(f"Cao nhất: Sensor #{int(top_sensor['grid_id'])} - {top_sensor['smoke']}")
            ], color="warning", className="mb-2 py-2")
        )
    
    if not critical:
        critical.append(
            dbc.Alert([
                html.I(className="fas fa-check-circle me-2"),
                "Hệ thống hoạt động bình thường"
            ], color="success", className="py-2")
        )
    
    # Top Temperature
    top_temp = df.nlargest(5, "temperature")
    temp_items = [
        dbc.ListGroupItem([
            html.Div([
                html.Strong(f"Sensor #{int(row['grid_id'])}", className="me-2"),
                html.Span(f"{row['temperature']:.1f}°C", className="float-end badge bg-danger")
            ]),
            dbc.Progress(value=min(row['temperature'], 40), max=40, color="danger", className="mt-2", style={"height": "6px"})
        ], className="py-2")
        for _, row in top_temp.iterrows()
    ]
    
    # Low Battery
    low_batt = df[df["battery"] < 30].sort_values("battery")
    if len(low_batt) > 0:
        batt_items = [
            dbc.ListGroupItem([
                html.Div([
                    html.Strong(f"Sensor #{int(row['grid_id'])}", className="me-2"),
                    html.Span(f"{row['battery']}%", className="float-end badge bg-warning text-dark")
                ]),
                dbc.Progress(value=row['battery'], max=100, color="warning", className="mt-2", style={"height": "6px"})
            ], className="py-2")
            for _, row in low_batt.head(5).iterrows()
        ]
    else:
        batt_items = [
            dbc.ListGroupItem([
                html.I(className="fas fa-battery-full me-2"),
                "Tất cả sensor pin tốt (>30%)"
            ], color="success", className="py-2")
        ]
    
    # Statistics
    stats = dbc.Row([
        dbc.Col([
            html.Div([
                html.Small("Nhiệt độ TB", className="text-muted d-block mb-1"),
                html.H5(f"{df['temperature'].mean():.1f}°C", className="mb-0 text-danger")
            ], className="stat-box text-center")
        ], xs=6, className="mb-2"),
        dbc.Col([
            html.Div([
                html.Small("Độ ẩm TB", className="text-muted d-block mb-1"),
                html.H5(f"{df['humidity'].mean():.1f}%", className="mb-0 text-info")
            ], className="stat-box text-center")
        ], xs=6, className="mb-2"),
        dbc.Col([
            html.Div([
                html.Small("CO₂ TB", className="text-muted d-block mb-1"),
                html.H5(f"{df['co2'].mean():.0f}ppm", className="mb-0 text-success")
            ], className="stat-box text-center")
        ], xs=6, className="mb-2"),
        dbc.Col([
            html.Div([
                html.Small("Tổng sensor", className="text-muted d-block mb-1"),
                html.H5(f"{len(df)}", className="mb-0 text-warning")
            ], className="stat-box text-center")
        ], xs=6, className="mb-2"),
    ], className="g-2")
    
    return critical, dbc.ListGroup(temp_items, flush=True), dbc.ListGroup(batt_items, flush=True), stats


@app.callback(
    Output("selected-sensor", "data"),
    Output("sensor-info-header", "children"),
    Output("sensor-detail-placeholder", "children"),
    Input("map-chart", "clickData"),
    Input("grid-store", "data")
)
def show_sensor_detail(clickData, grid_json):
    if not clickData or not grid_json:
        return None, "", html.Div([
            html.Div([
                html.I(className="fas fa-mouse-pointer", style={"fontSize": "48px", "color": "#6c757d"}),
                html.P("Nhấp vào sensor trên bản đồ để xem thông tin chi tiết", 
                      className="text-muted mt-3")
            ], className="text-center py-5")
        ])
    
    # Fix: Check if location exists and is not None
    try:
        point_data = clickData["points"][0]
        if "customdata" in point_data and point_data["customdata"] is not None:
            grid_id = int(point_data["customdata"][0])
        elif "location" in point_data and point_data["location"] is not None:
            grid_id = int(point_data["location"])
        else:
            # Return empty state if no valid data
            return None, "", html.Div([
                html.Div([
                    html.I(className="fas fa-mouse-pointer", style={"fontSize": "48px", "color": "#6c757d"}),
                    html.P("Nhấp vào sensor trên bản đồ để xem thông tin chi tiết", 
                          className="text-muted mt-3")
                ], className="text-center py-5")
            ])
    except (KeyError, TypeError, ValueError):
        return None, "", html.Div([
            html.Div([
                html.I(className="fas fa-mouse-pointer", style={"fontSize": "48px", "color": "#6c757d"}),
                html.P("Nhấp vào sensor trên bản đồ để xem thông tin chi tiết", 
                      className="text-muted mt-3")
            ], className="text-center py-5")
        ])
    
    df = pd.read_json(grid_json, orient="split")
    sensor = df[df["grid_id"] == grid_id].iloc[0]
    
    # Header info
    header_info = html.Span([
        html.Span(f"Sensor #{grid_id}", className="me-2 fw-bold"),
        dbc.Badge(f"🔋 {sensor['battery']}%", 
                 color="success" if sensor['battery'] > 50 else "warning" if sensor['battery'] > 30 else "danger",
                 className="me-1"),
        dbc.Badge(f"🌡️ {sensor['temperature']:.1f}°C", 
                 color="danger" if sensor['temperature'] > 32 else "secondary")
    ])
    
    # Detailed charts
    days = pd.date_range(end=pd.Timestamp.today(), periods=30)
    base_temp = sensor['temperature']
    base_hum = sensor['humidity']
    base_co2 = sensor['co2']
    
    history = pd.DataFrame({
        "Ngày": days,
        "Nhiệt độ": base_temp + np.sin(np.arange(30)/3) * 2 + np.random.normal(0, 0.5, 30),
        "Độ ẩm": base_hum + np.cos(np.arange(30)/4) * 3 + np.random.normal(0, 1, 30),
        "CO₂": base_co2 + np.random.normal(0, 5, 30),
        "Khói": sensor['smoke'] + np.random.randint(-10, 10, 30)
    })
    
    chart_layout = dict(
        paper_bgcolor="#2a2a2a", 
        plot_bgcolor="#2a2a2a", 
        font_color="white", 
        height=250,
        margin=dict(l=40, r=20, t=40, b=40)
    )
    
    detail_content = dbc.Row([
        dbc.Col([
            dcc.Graph(
                figure=px.line(history, x="Ngày", y="Nhiệt độ", title="📈 Nhiệt độ 30 ngày")
                .update_layout(**chart_layout)
                .update_traces(line_color="#ff6b6b"),
                config={"displayModeBar": False}
            )
        ], lg=6, md=12, className="mb-3"),
        dbc.Col([
            dcc.Graph(
                figure=px.line(history, x="Ngày", y="Độ ẩm", title="💧 Độ ẩm 30 ngày")
                .update_layout(**chart_layout)
                .update_traces(line_color="#4ecdc4"),
                config={"displayModeBar": False}
            )
        ], lg=6, md=12, className="mb-3"),
        dbc.Col([
            dcc.Graph(
                figure=px.line(history, x="Ngày", y="CO₂", title="🏭 CO₂ 30 ngày")
                .update_layout(**chart_layout)
                .update_traces(line_color="#95e1d3"),
                config={"displayModeBar": False}
            )
        ], lg=6, md=12, className="mb-3"),
        dbc.Col([
            dcc.Graph(
                figure=px.line(history, x="Ngày", y="Khói", title="💨 Khói 30 ngày")
                .update_layout(**chart_layout)
                .update_traces(line_color="#ffd93d"),
                config={"displayModeBar": False}
            )
        ], lg=6, md=12, className="mb-3"),
    ], className="g-2")
    
    return grid_id, header_info, detail_content


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=8051)