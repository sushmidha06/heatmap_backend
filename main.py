from fastapi import FastAPI, UploadFile, File, HTTPException
import numpy as np
import rasterio
import shutil
import os
import tempfile
from PIL import Image
from rasterio.errors import RasterioIOError

app = FastAPI()

# Constants
BIOMASS_COEF_A = 25
BIOMASS_COEF_B = 5
CARBON_FRACTION = 0.475
CO2_CONVERSION = 3.67
PIXEL_AREA_HA = 0.09

@app.get("/")
def read_root():
    return {"message": "Heatmap Backend is running! Use POST /calculate_credits/ with a file."}

@app.post("/calculate_credits/")
async def calculate_credits(file: UploadFile = File(...)):
    # Validate file type
    allowed_types = ["image/tiff", "image/jpeg", "image/png"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="File must be TIFF, JPG, or PNG")

    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.filename}") as tmp:
        shutil.copyfileobj(file.file, tmp)
        file_location = tmp.name

    try:
        # Convert JPG/PNG to GeoTIFF if needed
        if file.filename.lower().endswith((".jpg", ".jpeg", ".png")):
            img = Image.open(file_location).convert("L")  # grayscale
            tif_location = file_location.rsplit(".", 1)[0] + ".tif"

            # Convert to numpy
            img_array = np.array(img)

            # Save as GeoTIFF
            height, width = img_array.shape
            transform = rasterio.transform.from_origin(0, 0, 1, 1)  # dummy georeference
            with rasterio.open(
                tif_location,
                "w",
                driver="GTiff",
                height=height,
                width=width,
                count=1,
                dtype=img_array.dtype,
                crs="+proj=latlong",
                transform=transform,
            ) as dst:
                dst.write(img_array, 1)

            os.remove(file_location)  # remove original jpg/png
            file_location = tif_location

        # Read raster file
        with rasterio.open(file_location) as src:
            heatmap = src.read(1)
            heatmap = np.where(heatmap > 0, heatmap, 0)  # filter invalid values

        # Step 1: Biomass estimation
        biomass_ha = BIOMASS_COEF_A * heatmap + BIOMASS_COEF_B

        # Step 2: Biomass per pixel
        biomass_pixel = biomass_ha * PIXEL_AREA_HA

        # Step 3: Convert to carbon stock
        carbon_pixel = biomass_pixel * CARBON_FRACTION

        # Step 4: Convert to CO2 equivalent
        co2_pixel = carbon_pixel * CO2_CONVERSION

        # Step 5: Total sequestration
        total_co2_sequestered = np.nansum(co2_pixel)

        # Step 6: Carbon credits
        carbon_credits = total_co2_sequestered / 1.0

        return {
            "total_CO2_sequestered_tonnes": round(float(total_co2_sequestered), 2),
            "carbon_credits": round(float(carbon_credits), 2)
        }

    except RasterioIOError:
        raise HTTPException(status_code=400, detail="Invalid raster or image format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(file_location):
            os.remove(file_location)
