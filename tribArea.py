import streamlit as st
import fitz  # PyMuPDF
import pandas as pd
import matplotlib.pyplot as plt
from shapely.geometry import Polygon, Point, LineString, MultiPoint
from shapely.ops import voronoi_diagram
import more_itertools
import io

# Scaling function
def scale_pdf(pdf_scale, dpi=72):
    inches_to_mm = 25.4
    pixel_size_mm = inches_to_mm / dpi
    return pixel_size_mm * pdf_scale

# Function to extract wall shapes
def wall_shapes(doc, scaling_factor):
    wall_shapes = []
    for page in doc:
        for drawing in page.get_drawings():
            if drawing['width'] == 2.0:
                points = [(seg[1][0], seg[1][1]) for seg in drawing.get('items', [])]
                unique_points = [points[0]] + [p for i, p in enumerate(points[1:]) if p != points[i]]
                scaled_points = [(x * scaling_factor, y * scaling_factor) for x, y in unique_points]
                wall_shapes.append(Polygon(LineString(scaled_points)))
    return wall_shapes

# Function to extract slab shapes
def slab_shapes(doc, scaling_factor):
    for page in doc:
        for drawing in page.get_drawings():
            if drawing['width'] == 1.0:
                points = [(seg[1][0], seg[1][1]) for seg in drawing.get('items', [])]
                unique_points = [points[0]] + [p for i, p in enumerate(points[1:]) if p != points[i]]
                scaled_points = [(x * scaling_factor, y * scaling_factor) for x, y in unique_points]
                return Polygon(scaled_points)
    return None

# Function to extract column shapes
def column_shapes(doc, scaling_factor):
    columns = []
    for page in doc:
        for drawing in page.get_drawings():
            if drawing['width'] == 3.0 and drawing.get("rect"):
                x0, y0, x1, y1 = drawing["rect"]
                points = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
                scaled_points = [(x * scaling_factor, y * scaling_factor) for x, y in points]
                columns.append(Polygon(scaled_points))
    return columns

# Function to create Voronoi diagram
def create_voronoi(slab_outline, columns, walls):
    column_centroids = [(col.centroid.x, col.centroid.y) for col in columns]
    wall_points = list(more_itertools.flatten([list(wall.exterior.coords) for wall in walls])) if walls else []
    combined_points = column_centroids + wall_points
    voronoi_source = MultiPoint(combined_points)
    voronoi_polygons = voronoi_diagram(voronoi_source)
    return [slab_outline.intersection(poly) for poly in voronoi_polygons.geoms]

# Function to generate the DataFrame
def get_voronoi_areas(columns, voronoi_polygons):
    return pd.DataFrame({"Column_Tag": [f"C_{i}" for i in range(len(columns))], "Area (m²)": [poly.area / 1e6 for poly in voronoi_polygons]})

# Streamlit UI
st.title("Building Elements Analyzer")
uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

if uploaded_file:
    doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
    scale_factor = scale_pdf(100, 72)
    
    slab = slab_shapes(doc, scale_factor)
    columns = column_shapes(doc, scale_factor)
    walls = wall_shapes(doc, scale_factor)
    
    if slab and columns:
        voronoi_polygons = create_voronoi(slab, columns, walls)
        area_df = get_voronoi_areas(columns, voronoi_polygons)
        
        # Plot elements
        fig, ax = plt.subplots(figsize=(10, 10))
        for col in columns:
            x, y = col.exterior.xy
            ax.fill(x, y, color="gray", alpha=0.7, label="Column")
        for wall in walls:
            x, y = wall.exterior.xy
            ax.plot(x, y, color="black", linewidth=2, label="Wall")
        for poly in voronoi_polygons:
            x, y = poly.exterior.xy
            ax.fill(x, y, color="orange", alpha=0.3)
        x, y = slab.exterior.xy
        ax.fill(x, y, color="lightblue", alpha=0.5, label="Slab")
        ax.legend()
        st.pyplot(fig)
        
        # Display and download area data
        st.write("### Voronoi Cell Areas")
        st.dataframe(area_df)
        csv = area_df.to_csv(index=False).encode('utf-8')
        st.download_button("Download CSV", csv, "voronoi_areas.csv", "text/csv")
