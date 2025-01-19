import streamlit as st
import matplotlib.pyplot as plt
from papermodels.paper.pdf import load_pdf_annotations
from papermodels.paper.plot import plot_annotations
from papermodels.paper.annotations import scale_annotations, filter_annotations, annotations_to_shapely
from decimal import Decimal
from shapely.geometry import GeometryCollection, MultiPoint, MultiPolygon, Polygon, Point, LineString
import shapely

# Function to plot Shapely geometries
def plot_geometry(ax, geometry, **kwargs):
    """Plot Shapely geometry on a Matplotlib Axes."""
    if isinstance(geometry, Point):
        ax.plot(geometry.x, geometry.y, 'o', **kwargs)
    elif isinstance(geometry, LineString):
        x, y = geometry.xy
        ax.plot(x, y, **kwargs)
    elif isinstance(geometry, Polygon):
        x, y = geometry.exterior.xy
        ax.plot(x, y, **kwargs)
        # Plot holes if present
        for interior in geometry.interiors:
            x_int, y_int = interior.xy
            ax.plot(x_int, y_int, linestyle='--', color=kwargs.get("color", "gray"))
    elif isinstance(geometry, MultiPolygon) or isinstance(geometry, GeometryCollection):
        for geom in geometry.geoms:
            plot_geometry(ax, geom, **kwargs)

# Streamlit app
st.title("Trib Area Viewer")
st.write("Upload a PDF file containing annotations.")

# File upload
uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])
if uploaded_file is not None:
    # Process the uploaded file
    with open("temp.pdf", "wb") as f:
        f.write(uploaded_file.getbuffer())

    try:
        # Load annotations
        annots = load_pdf_annotations("temp.pdf")
        st.write("Loaded Annotations:", annots)


        # Scale annotations (1:50, convert from points to mm)
        scaled = scale_annotations(annots, Decimal(1 / 72 * 25.4 * 100))
        st.write("Scaled Annotations:", [annot for annot in scaled])

        # Filter annotations for columns and slab
        columns = filter_annotations(scaled, {"object_type": "Rectangle", "line_weight": 3})
        slab = filter_annotations(scaled, {"object_type": "Polygon", "text": "Slab Outline"})
        st.write("Filtered Columns:", columns)
        st.write("Filtered Slab:", slab)

        # Convert annotations to Shapely geometries
        column_shapes = annotations_to_shapely(columns, as_geometry_collection=True)
        slab_shapes = annotations_to_shapely(slab, as_geometry_collection=True)
        st.write("Column Shapes:", [col.bounds for col in column_shapes.geoms])
        st.write("Slab Shape Bounds:", slab_shapes.bounds)

        # Create column centroids and Voronoi polygons
        column_centroids = MultiPoint([column.centroid for column in column_shapes.geoms])
        vor_polys = shapely.voronoi_polygons(column_centroids)
        st.write("Voronoi Polygons:", [vor.bounds for vor in vor_polys.geoms])

        # Clip Voronoi polygons to slab shape
        trib_areas = MultiPolygon([
            vor_poly.intersection(slab_shapes)
            for vor_poly in vor_polys.geoms
            if not vor_poly.is_empty
        ])
        st.write("Clipped Polygons (Trib Areas):", [poly.bounds for poly in trib_areas.geoms])

        # Plot the Voronoi diagram with debugging
        import matplotlib
        matplotlib.use("Agg")  # Use Agg backend for consistent rendering

        fig, ax = plt.subplots(figsize=(10, 10), dpi=100)

        for geometry in trib_areas.geoms:
            if isinstance(geometry, Polygon) and not geometry.is_empty:
                plot_geometry(ax, geometry, color='blue', alpha=0.3, linewidth=1)

                # Annotate area
                area = geometry.area
                centroid = geometry.centroid
                ax.text(
                    centroid.x, centroid.y,
                    f"{area:.2f}",
                    ha='center', va='center', fontsize=8, color='red'
                )

        for column in column_shapes.geoms:
            ax.plot(column.centroid.x, column.centroid.y, 'ro', label='Column Centroid')

        # Standardize plot limits
        all_bounds = [geom.bounds for geom in trib_areas.geoms if not geom.is_empty]
        x_min = min([b[0] for b in all_bounds])
        y_min = min([b[1] for b in all_bounds])
        x_max = max([b[2] for b in all_bounds])
        y_max = max([b[3] for b in all_bounds])
        ax.set_xlim(x_min, x_max)
        ax.set_ylim(y_min, y_max)
        ax.set_aspect('equal')

        fig.savefig("debug_plot_streamlit.png", dpi=100, bbox_inches="tight")
        st.image("debug_plot_streamlit.png")

    except Exception as e:
        st.error(f"An error occurred: {e}")
