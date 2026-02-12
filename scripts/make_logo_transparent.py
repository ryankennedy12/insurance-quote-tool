"""
Remove maroon background from logo and create transparent PNG.
Samples corner pixels to detect background color and replaces similar colors with transparency.
"""

from PIL import Image
import numpy as np
from pathlib import Path


def make_logo_transparent(input_path: str, output_path: str, tolerance: int = 30):
    """
    Remove maroon background from logo and save with transparency.

    Args:
        input_path: Path to input logo (PNG/JPG)
        output_path: Path to save transparent PNG
        tolerance: Color distance threshold for background detection (0-255)
    """
    # Load image
    img = Image.open(input_path).convert("RGBA")
    data = np.array(img)

    # Sample background color from corner pixels (average of 4 corners)
    corners = [
        data[0, 0],           # top-left
        data[0, -1],          # top-right
        data[-1, 0],          # bottom-left
        data[-1, -1],         # bottom-right
    ]
    bg_color = np.mean(corners, axis=0)[:3]  # Average RGB (ignore alpha)

    print(f"Detected background color: RGB{tuple(bg_color.astype(int))}")

    # Calculate color distance for each pixel
    r, g, b, a = data[:, :, 0], data[:, :, 1], data[:, :, 2], data[:, :, 3]
    color_distance = np.sqrt(
        (r - bg_color[0]) ** 2 +
        (g - bg_color[1]) ** 2 +
        (b - bg_color[2]) ** 2
    )

    # Replace background pixels with transparency
    mask = color_distance <= tolerance
    data[mask, 3] = 0  # Set alpha to 0 for background pixels

    pixels_made_transparent = np.sum(mask)
    total_pixels = data.shape[0] * data.shape[1]
    pct = (pixels_made_transparent / total_pixels) * 100

    print(f"Made {pixels_made_transparent:,} pixels transparent ({pct:.1f}%)")

    # Save transparent PNG
    result = Image.fromarray(data, mode="RGBA")
    result.save(output_path, "PNG")
    print(f"Saved: {output_path}")

    return output_path


if __name__ == "__main__":
    input_logo = "assets/logo_rgb.png"
    output_logo = "assets/logo_transparent.png"

    print("=" * 60)
    print("Logo Background Removal")
    print("=" * 60)
    print(f"Input:  {input_logo}")
    print(f"Output: {output_logo}")
    print()

    # Check input exists
    if not Path(input_logo).exists():
        print(f"ERROR: {input_logo} not found")
        exit(1)

    # Process
    make_logo_transparent(input_logo, output_logo, tolerance=30)

    print()
    print("=" * 60)
    print("Done! Logo background removed successfully.")
    print("=" * 60)
