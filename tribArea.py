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

        # Scale annotations (1:50, convert from points to mm)
        scaled = scale_annotations(annots, Decimal(1 / 72 * 25.4 * 100))

        # Filter annotations for columns and slab
        columns = filter_annotations(scaled, {"object_type": "Rectangle", "line_weight": 3})
        slab = filter_annotations(scaled, {"object_type": "Polygon", "text": "Slab Outline"})

        # Convert annotations to Shapely geometries
        column_shapes = annotations_to_shapely(columns, as_geometry_collection=True)
        slab_shapes = annotations_to_shapely(slab, as_geometry_collection=True)

        # Create column centroids and Voronoi polygons
        column_centroids = MultiPoint([column.centroid for column in column_shapes.geoms])
        vor_polys = shapely.voronoi_polygons(column_centroids)

        # Clip Voronoi polygons to slab shape
        trib_areas = MultiPolygon([
            vor_poly.intersection(slab_shapes)
            for vor_poly in vor_polys.geoms
            if not vor_poly.is_empty
        ])

        # Plot the Voronoi diagram
        fig, ax = plt.subplots(figsize=(10, 10), dpi=100)

        # Plot the Voronoi polygons (trib_areas)
        for geometry in trib_areas.geoms:
            if isinstance(geometry, Polygon) and not geometry.is_empty:
                # Plot the geometry
                plot_geometry(ax, geometry, color='blue', alpha=0.3, linewidth=1)

                # Calculate and annotate area
                area = geometry.area
                centroid = geometry.centroid
                ax.text(
                    centroid.x, centroid.y,
                    f"{area:.2f}",  # Format the area to 2 decimal places
                    ha='center', va='center', fontsize=8, color='red'
                )

        # Plot column centroids
        for column in column_shapes.geoms:
            ax.plot(column.centroid.x, column.centroid.y, 'ro', label='Column Centroid')

        # Set consistent axis limits
        x_min, y_min, x_max, y_max = slab_shapes.bounds
        ax.set_xlim(x_min, x_max)
        ax.set_ylim(y_min, y_max)

        # Set aspect ratio and labels
        ax.set_aspect('equal')
        ax.set_xlabel("X (mm)")
        ax.set_ylabel("Y (mm)")
        ax.set_title("Voronoi Diagram with Area Annotations")

        # Save the figure (optional for debugging)
        fig.savefig("debug_plot.png", bbox_inches="tight", dpi=100)

        # Display the plot in Streamlit
        st.pyplot(fig, bbox_inches="tight")

    except Exception as e:
        st.error(f"An error occurred: {e}")