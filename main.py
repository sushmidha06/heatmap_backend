from fastapi import FastAPI, UploadFile, File, HTTPException
import numpy as np
import rasterio
import shutil
import os

app = FastAPI()

# Constants
BIOMASS_COEF_A = 25       # Adjusted regression coefficient 
BIOMASS_COEF_B = 5        # Adjusted intercept
CARBON_FRACTION = 0.475
CO2_CONVERSION = 3.67
PIXEL_AREA_HA = 0.09      # 30m x 30m pixel area

@app.post("/calculate_credits/")
async def calculate_credits(file: UploadFile = File(...)):
    try:
        # Save uploaded file temporarily
        file_location = f"temp_{file.filename}"
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Read raster file
        with rasterio.open(file_location) as src:
            heatmap = src.read(1)
            heatmap = np.where(heatmap > 0, heatmap, 0)  # Filter invalid values

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

        # Clean up temp file
        os.remove(file_location)

        return {
            "total_CO2_sequestered_tonnes": round(float(total_co2_sequestered), 2),
            "carbon_credits": round(float(carbon_credits), 2)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
