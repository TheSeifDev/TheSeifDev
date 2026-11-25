from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
HTML = ROOT / "profile-hero.html"
OUTPUT = ROOT / "profile-hero.gif"
WIDTH, HEIGHT = 960, 300
FRAME_COUNT = 40
FRAME_MS = 100  # 40 frames × 100 ms = one four-second loop


def main() -> None:
    with TemporaryDirectory(prefix="profile-hero-") as temp_dir:
        frame_paths = [Path(temp_dir) / f"frame-{i:03}.png" for i in range(FRAME_COUNT)]
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path="/usr/bin/chromium",
                args=["--no-sandbox"],
            )
            page = browser.new_page(
                viewport={"width": WIDTH, "height": HEIGHT},
                device_scale_factor=1,
            )
            page.goto(HTML.as_uri(), wait_until="load")
            page.locator(".poster").wait_for()
            page.wait_for_function(
                """() => {
                    const image = document.querySelector('.portrait');
                    return image && image.complete && image.naturalWidth > 0;
                }"""
            )
            page.evaluate("document.fonts.ready")
            page.wait_for_timeout(150)

            for index, frame_path in enumerate(frame_paths):
                timestamp = index * FRAME_MS
                page.evaluate(
                    """(time) => document.getAnimations().forEach((animation) => {
                        animation.pause();
                        animation.currentTime = time;
                    })""",
                    timestamp,
                )
                page.locator(".poster").screenshot(path=str(frame_path), animations="allow")
            browser.close()

        rgb_frames = [Image.open(path).convert("RGB") for path in frame_paths]
        palette_sheet = Image.new("RGB", (WIDTH, HEIGHT * FRAME_COUNT))
        for index, frame in enumerate(rgb_frames):
            palette_sheet.paste(frame, (0, index * HEIGHT))

        palette = palette_sheet.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
        gif_frames = [
            frame.quantize(palette=palette, dither=Image.Dither.FLOYDSTEINBERG)
            for frame in rgb_frames
        ]
        unoptimized = Path(temp_dir) / "profile-hero.gif"
        gif_frames[0].save(
            unoptimized,
            save_all=True,
            append_images=gif_frames[1:],
            duration=FRAME_MS,
            loop=0,
            optimize=True,
            disposal=2,
        )

        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("FFmpeg is required to optimize the animated GIF for GitHub.")
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(unoptimized),
                "-vf",
                "split[s0][s1];[s0]palettegen=max_colors=80:stats_mode=diff[p];"
                "[s1][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle",
                "-loop",
                "0",
                "-f",
                "gif",
                str(OUTPUT),
            ],
            check=True,
        )

    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
