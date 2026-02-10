import fiona
import geopandas as gpd

gpkg_path = "or_huc_geopackage.gpkg"   # <-- change this

# 1) List layers
layers = fiona.listlayers(gpkg_path)
print("Layers in GPKG:")
for i, lyr in enumerate(layers):
    print(f"  {i}: {lyr}")

# 2) Load each layer and show summary
for lyr in layers:
    gdf = gpd.read_file(gpkg_path, layer=lyr)
    print("\n" + "="*60)
    print("Layer:", lyr)
    print("Rows:", len(gdf))
    print("CRS:", gdf.crs)
    print("Geometry type(s):", gdf.geom_type.unique())
    print("Columns:", list(gdf.columns))
    print("Sample:")
    print(gdf.head(3))
