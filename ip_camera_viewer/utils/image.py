from PIL import Image


def frame_to_canvas(frame, max_width: int, max_height: int) -> Image.Image:
    image = Image.fromarray(frame)
    image.thumbnail((max_width, max_height), Image.LANCZOS)

    canvas = Image.new("RGB", (max_width, max_height), "black")
    x = (max_width - image.width) // 2
    y = (max_height - image.height) // 2
    canvas.paste(image, (x, y))
    return canvas
