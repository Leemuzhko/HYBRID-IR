"""Storage accounting, not a firmware allocation or CPU guarantee."""
from dataclasses import replace
import sys

from .zoom_bank import SDK, SOFT_CONST_BYTES, pack_bank


def align_up(value, alignment):
    return (value + alignment - 1) // alignment * alignment


def picture_bytes(path):
    from PIL import Image
    if str(SDK / 'build') not in sys.path:sys.path.insert(0, str(SDK / 'build'))
    from screen_image import Canvas, encode_zoom_rle
    with Image.open(path) as source:
        image = source.convert('L')
    if image.size != (128, 64) or not set(image.tobytes()) <= {0, 255}:
        raise ValueError('PNG must contain 128x64 black/white pixels')
    canvas = Canvas()
    canvas.pixels = [[int(image.getpixel((x, y)) == 0) for x in range(128)] for y in range(64)]
    return encode_zoom_rle(canvas)


def const_bytes(bank_bytes, image_bytes):
    # Current nine-parameter HYBRIDIR linker layout. No custom sprite tails.
    # image, aligned SonicStomp (11*48), imageInfo (212), dummy coe (68), bank.
    prefix = align_up(align_up(image_bytes, 4) + 528 + 212 + 68, 8)
    return align_up(prefix + bank_bytes, 8)


def bank_usage(project):
    """Preview capacity independently of partially typed display names/IDs."""
    if project.slots:
        _, report = pack_bank(replace(project, name='HYBRID IR', filename='HYBRIDIR', fxid=565))
    else:
        report = dict(bank_bytes=2816, active_slots=0, fir_pool_samples=2,
                      bq_pool_sections=2, max_fir=32, max_bq=2,
                      estimated_state_bytes=560)
    image_size = len(picture_bytes(project.image))
    used = const_bytes(report['bank_bytes'], image_size)
    from .zoom_patch import load_template
    _, _, profile = load_template()
    c = profile['capacity']
    limits = dict(slots=(len(project.slots), c['entry_count'] - 1),
                  fir_pool=(report['fir_pool_samples'], c['fir_pool_samples']),
                  bq_pool=(report['bq_pool_sections'], c['bq_pool_sections']),
                  max_fir=(report['max_fir'], c['max_fir']),
                  max_bq=(report['max_bq'], c['max_bq']),
                  image=(image_size, profile['regions']['image'][1]))
    return dict(report, const_bytes=used, const_budget=SOFT_CONST_BYTES,
                remaining_bytes=SOFT_CONST_BYTES-used, image_bytes=image_size,
                control_table_bytes=2440, limits=limits,
                template_fraction=max(n / limit for n, limit in limits.values()),
                template_fits=all(n <= limit for n, limit in limits.values()),
                hardware_validated=False)
