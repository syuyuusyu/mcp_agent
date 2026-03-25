from PIL import Image
from pathlib import Path

base = Path("/Users/syu/project/ml/ai_chat/agent-box/agent-box/Assets.xcassets/AppIcon.appiconset")
files = ["AppIcon.png", "AppIcon-dark.png", "AppIcon-tinted.png"]

for name in files:
    p = base / name
    im = Image.open(p)
    # 如果有透明通道，先贴到不透明背景上；没有就直接转 RGB
    if im.mode in ("RGBA", "LA") or ("transparency" in im.info):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        alpha = im.split()[-1] if im.mode in ("RGBA", "LA") else None
        if alpha is not None:
            bg.paste(im.convert("RGBA"), mask=alpha)
        else:
            bg.paste(im.convert("RGBA"))
        out = bg
    else:
        out = im.convert("RGB")

    # 强制写出不带 alpha 的 PNG
    out.save(p, format="PNG", optimize=True)

print("Done. Icons rewritten as RGB (no alpha).")
