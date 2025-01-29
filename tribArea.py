import fitz  # PyMuPDF
from shapely.geometry import Polygon, LineString, LinearRing

from papermodels.paper.pdf import load_pdf_annotations
from papermodels.paper.plot import plot_annotations
from papermodels.paper.annotations import scale_annotations, filter_annotations, annotations_to_shapely

from decimal import Decimal
import matplotlib

import shapely
from shapely import wkt, voronoi_polygons
from shapely.ops import voronoi_diagram
from shapely.geometry import GeometryCollection as GC
from shapely.geometry import MultiPolygon
from shapely.geometry import MultiPoint as MP
import matplotlib.pyplot as plt
from shapely.geometry import Polygon, MultiPolygon, GeometryCollection, Point, LineString, Polygon
from shapely.affinity import rotate, scale

import streamlit as st
import pandas as pd


import more_itertools # This library is included in PfSE. Look it up on PyPI for docs (useful)

# Scaling function
def scale_pdf(pdf_scale , dpi=72):
    # Conversion factor: inches to mm
    inches_to_mm = 25.4

    # Calculate the pixel-to-mm scaling factor
    pixel_size_mm = inches_to_mm / dpi
    scaling_factor = pixel_size_mm * pdf_scale
    return scaling_factor

# Function to extract wall shapes
def wall_shapes(doc, pdf_scale):

    #Scaling Factor#
    scaling_factor = scale_pdf(100, 72)
    
    # Iterate through all pages
    for page in doc:
        # Extract all vector drawings on the page
        drawings = page.get_drawings()
        wall_shapes = []
    
        for drawing in drawings:
            if drawing['width'] == 2.0:
                # Extract line segments from the "l" key
                line_segments = drawing.get('items', [])
                points = []
                for segment in line_segments:
                    x1, y1 =  segment[1]
                    points.append((x1, y1))  # Add the starting point
        
                # Remove duplicate consecutive points
                unique_points = [points[0]]
                for point in points[1:]:
                    if point != unique_points[-1]:
                        unique_points.append(point)

                
                # Scale the coordinates to mm
                scaled_points = [(x * scaling_factor, y * scaling_factor) for x, y in unique_points]
        
                # Create a LinearRing from the scaled points
                wall_shapes.append(Polygon(LineString(scaled_points)))
                
    return wall_shapes

# Function to extract slab shapes
def slab_shapes(doc, pdf_scale):

    # Scaling factor for converting from PDF units to mm
    scaling_factor = scale_pdf(100, 72)

    # polygons = [] placeholder for multiple polygons##

    # Iterate through all pages in the PDF
    for page in doc:
        # Extract all vector drawings on the page
        drawings = page.get_drawings()

        for drawing in drawings:
            # Check for closed polyline annotations with a line width of 1.0
            if drawing['width'] == 1.0:
                # Extract line segments
                polygon_segments = drawing.get('items', [])
                points = []

                for segment in polygon_segments:
                    x1, y1 = segment[1]  # Start point of the segment
                    points.append((x1, y1))
                
                # Check if the polyline is closed
                if points:
                    # Remove duplicate consecutive points
                    unique_points = [points[0]]
                    for point in points[1:]:
                        if point != unique_points[-1]:
                            unique_points.append(point)
                    
                    # Scale the coordinates to mm
                    scaled_points = [(x * scaling_factor, y * scaling_factor) for x, y in unique_points]
                    
                    # Create a polygon from the scaled points
                    polygons = Polygon(scaled_points)

    return polygons

# Function to extract column shapes
def column_shapes(doc, pdf_scale):
    """
    Converts rectangle annotations with a line width of 3.0 in a PDF into Shapely polygons.
    
    Args:
        pdf_file (str): Path to the PDF file.
        pdf_scale (function): Function to scale PDF coordinates to real-world units (e.g., mm).
    
    Returns:
        list: A list of Shapely Polygon objects representing the rectangles.
    """

    # Scaling factor for converting from PDF units to mm
    scaling_factor = scale_pdf(100, 72)

    rectangles = []

    # Iterate through all pages in the PDF
    for page in doc:
        # Extract all vector drawings on the page
        drawings = page.get_drawings()

        for drawing in drawings:
            # Check for rectangle annotations with a line width of 3.0
            if drawing['width'] == 3.0:
                # Extract the rectangle's coordinates (assuming 'rect' key exists)
                rect = drawing.get("rect")
                if rect:
                    x0, y0, x1, y1 = rect  # Top-left and bottom-right coordinates
                    points = [
                        (x0, y0),  # Top-left
                        (x1, y0),  # Top-right
                        (x1, y1),  # Bottom-right
                        (x0, y1),  # Bottom-left
                        (x0, y0),  # Close the rectangle
                    ]

                    # Scale the coordinates to mm
                    scaled_points = [(x * scaling_factor, y * scaling_factor) for x, y in points]

                    # Create a Shapely Polygon from the scaled points
                    rectangles.append(Polygon(scaled_points))

    return rectangles

# Function to create Voronoi diagram
def create_voronoi(slab_outline, columns, walls=None):
    """
    Generate Voronoi diagrams based on the centroids of columns and optionally wall geometries.
    
    Args:
        slab_outline (Polygon): The boundary polygon to trim the Voronoi diagram.
        columns (list of Polygon): List of column geometries.
        walls (list of Polygon, optional): List of wall geometries. Defaults to None.

    Returns:
        list: A list of polygons representing the trimmed Voronoi cells.
    """
    # Get the centroids of the columns as points
    column_centroids = [(col.centroid.x, col.centroid.y) for col in columns]

    # Process walls if provided
    wall_points = []
    if walls:
        # Define the maximum segment length for wall segmentation
        max_segment_length = 300

        # Segmentize the walls and collect their exterior points
        segmented_walls = [shapely.segmentize(wall.exterior, max_segment_length) for wall in walls]
        wall_points = [list(wall.coords) for wall in segmented_walls]

    # Combine column centroids and wall points into a single list
    combined_points = column_centroids + list(more_itertools.flatten(wall_points))

    # Create a Voronoi diagram from the combined points
    voronoi_source = MP(combined_points)
    voronoi_polygons = voronoi_diagram(voronoi_source)

    # Trim the Voronoi polygons to fit within the slab outline
    trimmed_voronoi_cells = [slab_outline.intersection(voronoi_poly) for voronoi_poly in voronoi_polygons.geoms]

    return trimmed_voronoi_cells

# Order voronoi polys#
def order_voronoi(slab_outline, columns, walls, trib_components):

    # Get the centroids of the columns as points
    column_centroids = [(col.centroid.x, col.centroid.y) for col in columns]

    # Process walls if provided
    wall_points = []
    if walls:
        # Define the maximum segment length for wall segmentation
        max_segment_length = 300

        # Segmentize the walls and collect their exterior points
        segmented_walls = [shapely.segmentize(wall.exterior, max_segment_length) for wall in walls]
        wall_points = [list(wall.coords) for wall in segmented_walls]

    # Combine column centroids and wall points into a single list
    combined_points = column_centroids + list(more_itertools.flatten(wall_points))

    reordered_components = []
    for point in combined_points: # Iterate by points to prioritize point order
        for poly in trib_components:
            if poly.contains(Point(point)):
                reordered_components.append(poly)
    return reordered_components


# Function to generate the DataFrame
def get_voronoi_areas(columns, voronoi_polygons):
    """
    Generates a DataFrame with column tags and corresponding Voronoi cell areas.

    Args:
        columns (list): List of Shapely polygons representing columns.
        voronoi_polygons (list): List of Shapely polygons representing Voronoi cells.

    Returns:
        pd.DataFrame: A DataFrame with columns "Column_Tag" and "Area (mm²)".
    """
    data = []

    for idx, (column, voronoi) in enumerate(zip(columns, voronoi_polygons)):
        if isinstance(column, Polygon) and isinstance(voronoi, Polygon):
            column_tag = f"C_{idx}"  # Generate the tag for the column
            area = voronoi.area  # Calculate the Voronoi cell area
            data.append({"Column_Tag": column_tag, "Area (m²)": area / 1e6})  # Convert to m²

    return pd.DataFrame(data)

# Streamlit UI
st.title("Trib Area Viewer")
uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

if uploaded_file:

    # Read the uploaded file into memory as bytes
    pdf_bytes = uploaded_file.read()

    # Open the PDF from bytes instead of treating it as a file path
    doc = fitz.open("pdf", pdf_bytes)  

    scale_factor = scale_pdf(100, 72)
    
    slab = slab_shapes(doc, scale_factor)
    columns = column_shapes(doc, scale_factor)
    walls = wall_shapes(doc, scale_factor)
    
    if slab and columns and walls:
        voronoi_polygons = create_voronoi(slab, columns, walls)
        ordered_voronoi_polygons = order_voronoi(slab, columns, walls, voronoi_polygons)
        area_df = get_voronoi_areas(columns, ordered_voronoi_polygons)
        
        # Plot elements
        fig, ax = plt.subplots(figsize=(10, 10))

        # Plot slab outline
        if slab:
            x, y = slab.exterior.xy
            ax.fill(x, y, color="lightblue", alpha=0.5, label="Slab Outline")

        # Plot columns
        for column in columns:
            if isinstance(column, Polygon):
                x, y = column.exterior.xy
                ax.fill(x, y, color="gray", alpha=0.7, label="Column" if "Column" not in ax.get_legend_handles_labels()[1] else "")

        # Plot walls
        for wall in walls:
            if isinstance(wall, Polygon):
                x, y = wall.exterior.xy
                ax.plot(x, y, color="black", linewidth=2, label="Wall" if "Wall" not in ax.get_legend_handles_labels()[1] else "")

        # Plot Voronoi polygons and label each with "C_number"
        if voronoi_polygons:
            for idx, v_poly in enumerate(ordered_voronoi_polygons):
                if isinstance(v_poly, Polygon):
                    # Plot the Voronoi polygon
                    x, y = v_poly.exterior.xy
                    ax.fill(x, y, color="orange", alpha=0.3, label="Voronoi Cell" if "Voronoi Cell" not in ax.get_legend_handles_labels()[1] else "")

                    # Calculate and display the area
                    area = v_poly.area/1e6
                    centroid = v_poly.centroid
                    ax.text(centroid.x, centroid.y, f"{area:.2f}", color="red", fontsize=8, ha="center", va="center")

                    # Label each rectangle with "C_number"
                    name = f"C_{idx}"
                    centroid = v_poly.centroid
                    ax.text(centroid.x, centroid.y, name, color="blue", fontsize=8, ha="left", va="bottom")


        # Customize the plot
        ax.set_aspect("equal", adjustable="datalim")
        ax.legend(loc="upper right")
        ax.set_title("Building Elements with Voronoi Polygons")
        ax.set_xlabel("X (mm)")
        ax.set_ylabel("Y (mm)")

        st.pyplot(fig)
        
        # Display and download area data
        st.write("### Voronoi Cell Areas")
        st.dataframe(area_df)
        csv = area_df.to_csv(index=False).encode('utf-8')
        st.download_button("Download CSV", csv, "voronoi_areas.csv", "text/csv")
