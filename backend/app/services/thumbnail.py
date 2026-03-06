import io

from PIL import Image


def generate_thumbnail(image_data: bytes, width: int = 400, quality: int = 80) -> bytes:
    img = Image.open(io.BytesIO(image_data))
    ratio = width / img.width
    new_height = int(img.height * ratio)
    img = img.resize((width, new_height), Image.LANCZOS)

    output = io.BytesIO()
    img.save(output, format="WebP", quality=quality)
    return output.getvalue()
