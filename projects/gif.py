import re, glob, time, os
from PIL import Image
import pygame
from gway import gw


def animate(pattern, *, output_gif=None):
    resolved = gw.resource(pattern)
    if os.path.isdir(resolved):
        pngs = sorted(glob.glob(os.path.join(resolved, "*.png")))
        if not pngs:
            gw.abort(f"No .png files found in directory: {resolved}")
        sample_file = os.path.basename(pngs[0])
        base_dir = resolved
    else:
        sample_file = os.path.basename(resolved)
        base_dir = os.path.dirname(resolved) or "."

    # Detect [n] or “ - n” patterns (falls back to ctime sort)
    bracket = re.search(r'\[(\d+)\]', sample_file)
    dash    = re.search(r'^(.*?)([ \-_]+)(\d+)(\.png)$', sample_file)
    if bracket:
        pfx = sample_file.split(bracket.group(0))[0]
        sfx = sample_file.split(bracket.group(0))[1]
        rx  = re.compile(r'^' + re.escape(pfx) + r'\[(\d+)\]' + re.escape(sfx) + r'$')
        pat = f"{pfx}*{sfx}"
    elif dash:
        pfx = dash.group(1) + dash.group(2)
        sfx = dash.group(4)
        rx  = re.compile(r'^' + re.escape(pfx) + r'(\d+)' + re.escape(sfx) + r'$')
        pat = f"{pfx}*{sfx}"
    else:
        # No numbering → creation order
        fns = sorted(glob.glob(os.path.join(base_dir, "*.png")), key=os.path.getctime)
        if not fns:
            gw.abort(f"No .png files in {base_dir}")
        images = [Image.open(f).convert("RGBA") for f in fns]
        return _display_and_save(images, fns, _make_outpath(pattern, output_gif, base_dir))

    # Gather & sort numbered frames
    items = []
    for fn in glob.glob(os.path.join(base_dir, pat)):
        nm = os.path.basename(fn)
        m  = rx.match(nm)
        if m: items.append((int(m.group(1)), fn))
    if not items:
        gw.abort(f"No files matching pattern {pat!r}")
    items.sort(key=lambda x: x[0])
    fns = [fn for _, fn in items]
    images = [Image.open(fn).convert("RGBA") for fn in fns]

    return _display_and_save(images, fns, _make_outpath(pattern, output_gif, base_dir))


def _make_outpath(pattern, output_gif, base_dir):
    if output_gif:
        return output_gif
    base = os.path.basename(pattern.rstrip("/\\")) or "output"
    return os.path.join(base_dir, base + ".gif")


def _display_and_save(pil_images, frame_files, output_gif):
    # Helper: flatten transparent frames onto black
    def flatten_rgba(img):
        if img.mode != "RGBA":
            return img.convert("RGB")
        bg = Image.new("RGB", img.size, (0, 0, 0))
        bg.paste(img, mask=img.split()[3])
        return bg

    # 1) Show & time
    pygame.init()
    W, H = zip(*(im.size for im in pil_images))
    screen = pygame.display.set_mode((max(W), max(H)))
    pygame.display.set_caption("SPACE to advance")

    durations, last = [], None
    font = pygame.font.SysFont(None, 36)
    for i, img in enumerate(pil_images):
        surf = pygame.image.fromstring(img.tobytes(), img.size, img.mode)
        screen.fill((0,0,0)); screen.blit(surf,(0,0))
        screen.blit(font.render(f"Frame {i}",True,(255,255,255)),(10,10))
        pygame.display.flip()
        waiting = True
        while waiting:
            for e in pygame.event.get():
                if e.type==pygame.KEYDOWN and e.key==pygame.K_SPACE:
                    now = time.time()
                    if last is not None: durations.append(now-last)
                    last = now
                    waiting = False
                elif e.type==pygame.QUIT:
                    pygame.quit(); gw.abort("User closed window")
    pygame.quit()
    if len(durations)==len(pil_images)-1: durations.append(durations[-1])
    durations_ms = [int(d*1000) for d in durations]

    # 2) Flatten + global quantize
    flat = [flatten_rgba(im) for im in pil_images]
    master = flat[0].convert("P", palette=Image.ADAPTIVE, colors=256)
    pal   = [im.quantize(palette=master) for im in flat]

    # 3) Save full-frame, browser-compatible GIF
    pal[0].save(
        output_gif,
        save_all=True,
        append_images=pal[1:],
        duration=durations_ms,
        loop=0,
        disposal=1,
        optimize=True
    )
    print(f"Saved GIF → {output_gif}")
