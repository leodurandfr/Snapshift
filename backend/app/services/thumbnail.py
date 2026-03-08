import io

from PIL import Image


def generate_thumbnail(image_data: bytes, width: int = 400, quality: int = 80) -> bytes:
    img = Image.open(io.BytesIO(image_data))

    # Crop to 4:3 aspect ratio (top of page)
    target_height = int(img.width * 3 / 4)
    if target_height < img.height:
        img = img.crop((0, 0, img.width, target_height))

    # Resize to target width
    thumb_height = int(width * 3 / 4)
    img = img.resize((width, thumb_height), Image.LANCZOS)

    output = io.BytesIO()
    img.save(output, format="WebP", quality=quality)
    return output.getvalue()
