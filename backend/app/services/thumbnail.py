import io

from PIL import Image


def generate_thumbnail(image_data: bytes, size: int = 1280, quality: int = 80) -> bytes:
    img = Image.open(io.BytesIO(image_data))

    # Crop top of page to 1:1 square
    side = min(img.width, img.height)
    img = img.crop((0, 0, side, side))

    # Resize to target size
    img = img.resize((size, size), Image.LANCZOS)

    output = io.BytesIO()
    img.save(output, format="WebP", quality=quality)
    return output.getvalue()
