import cv2
import numpy as np
import os

def analyze_space_image(image_path: str):
    if not os.path.exists(image_path):
        return {"error": "Image not found"}
    image = cv2.imread(image_path)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Detect bright regions (stars, highlights)
    bright_mask = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)[1]

    # Detect edges (planet surfaces, craters, etc.)
    edges = cv2.Canny(gray, 100, 200)

    # Combine both for "interesting" map
    combined = cv2.addWeighted(bright_mask, 0.5, edges, 0.5, 0)

    # Find contours for regions
    contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    interesting_regions = []
    for cnt in contours[:10]: 
        x, y, w, h = cv2.boundingRect(cnt)
        interesting_regions.append({
            "x": int(x + w / 2),
            "y": int(y + h / 2),
            "desc": "Possible interesting feature (edge/bright region)"
        })

    return {
        "regions": interesting_regions,
        "count": len(interesting_regions)
    }
