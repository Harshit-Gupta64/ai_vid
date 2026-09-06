#!/usr/bin/env python3
"""
create_contact_sheet.py - Visual QA Contact Sheet Generator

Arranges generated vertical scene frames (9:16) into a unified visual contact sheet
stamped with scene ID, timecode, and camera motion metadata for rapid quality assurance.
"""

import argparse
import glob
import json
import os
import re
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def get_scene_metadata(storyboard_path: Path) -> dict:
    """Reads storyboard JSON to extract metadata keyed by scene_id."""
    meta = {}
    if storyboard_path.exists():
        try:
            with open(storyboard_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for sc in data.get("scenes", []):
                sid = sc.get("scene_id")
                if sid is not None:
                    meta[sid] = {
                        "time_range": sc.get("time_range", ""),
                        "camera_motion": sc.get("camera_motion", "static"),
                        "description": sc.get("visual_description", "")[:45]
                    }
        except Exception as e:
            print(f"[WARN] Could not parse storyboard metadata: {e}", file=sys.stderr)
    return meta


def create_contact_sheet(
    frames_dir: Path,
    storyboard_path: Path,
    output_path: Path,
    thumb_width: int = 360,
    thumb_height: int = 640,
    cols: int = 5,
    margin: int = 24,
    header_height: int = 80
):
    metadata = get_scene_metadata(storyboard_path)

    # Find scene frames matching scene_*.png
    pattern = str(frames_dir / "scene_*.png")
    frame_files = glob.glob(pattern)
    if not frame_files:
        print(f"[ERROR] No scene frames found in {frames_dir.resolve()}", file=sys.stderr)
        sys.exit(1)

    # Sort numerically by scene ID
    def extract_scene_id(path_str):
        m = re.search(r"scene_(\d+)", os.path.basename(path_str))
        return int(m.group(1)) if m else 999

    sorted_frames = sorted(frame_files, key=extract_scene_id)
    total_scenes = len(sorted_frames)

    # Calculate grid dimensions
    num_cols = min(cols, total_scenes)
    num_rows = (total_scenes + num_cols - 1) // num_cols

    grid_width = num_cols * thumb_width + (num_cols + 1) * margin
    grid_height = header_height + num_rows * thumb_height + (num_rows + 1) * margin

    # Create dark matte background
    sheet = Image.new("RGB", (grid_width, grid_height), color=(14, 14, 18))
    draw = ImageDraw.Draw(sheet)

    # Draw top header bar
    draw.rectangle([(0, 0), (grid_width, header_height)], fill=(22, 22, 28))
    draw.line([(0, header_height), (grid_width, header_height)], fill=(45, 45, 55), width=2)

    title_text = "TACTICAL STORYBOARD // VISUAL QA CONTACT SHEET"
    sub_text = f"{total_scenes} SCENES | 9:16 VERTICAL FRAMES | ENFORCED OIL PAINTING AESTHETIC"
    draw.text((margin, 18), title_text, fill=(240, 210, 140))
    draw.text((margin, 46), sub_text, fill=(160, 160, 175))

    # Font setup
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    for idx, fpath in enumerate(sorted_frames):
        scene_id = extract_scene_id(fpath)
        row = idx // num_cols
        col = idx % num_cols

        x_pos = margin + col * (thumb_width + margin)
        y_pos = header_height + margin + row * (thumb_height + margin)

        # Open and resize keyframe
        with Image.open(fpath) as img:
            thumb = img.convert("RGB").resize((thumb_width, thumb_height), Image.Resampling.LANCZOS)

        tdraw = ImageDraw.Draw(thumb)

        # Retrieve scene metadata
        sc_info = metadata.get(scene_id, {})
        time_str = sc_info.get("time_range", "")
        camera_str = sc_info.get("camera_motion", "vertical frame")
        desc_str = sc_info.get("description", "")

        # Top Badge: Scene Number and Timecode
        badge_top_h = 36
        badge_top = Image.new("RGBA", (thumb_width, badge_top_h), (10, 10, 15, 210))
        bdraw = ImageDraw.Draw(badge_top)
        header_label = f"SCENE {scene_id}" + (f"  [{time_str}]" if time_str else "")
        bdraw.text((12, 10), header_label, fill=(255, 255, 255), font=font)
        thumb.paste(badge_top, (0, 0), badge_top)

        # Bottom Badge: Camera Motion & Shot Info
        badge_bot_h = 52
        badge_bot = Image.new("RGBA", (thumb_width, badge_bot_h), (10, 10, 15, 220))
        bbdraw = ImageDraw.Draw(badge_bot)
        bbdraw.text((12, 8), f"MOTION: {camera_str.upper()}", fill=(230, 195, 110), font=font)
        if desc_str:
            bbdraw.text((12, 28), desc_str, fill=(200, 200, 200), font=font)
        thumb.paste(badge_bot, (0, thumb_height - badge_bot_h), badge_bot)

        # Subtle card border
        draw_border = ImageDraw.Draw(thumb)
        draw_border.rectangle([(0, 0), (thumb_width - 1, thumb_height - 1)], outline=(70, 70, 85), width=2)

        # Paste onto contact sheet
        sheet.paste(thumb, (x_pos, y_pos))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(str(output_path), "PNG")
    print(f"[SUCCESS] Contact sheet generated: {output_path.resolve()} ({grid_width}x{grid_height})")


def main():
    parser = argparse.ArgumentParser(description="Generate Visual QA Contact Sheet from scene keyframes.")
    parser.add_argument("--frames-dir", type=str, default="assets/frames", help="Directory containing scene_*.png images.")
    parser.add_argument("--storyboard", type=str, default="state/storyboard.json", help="Path to storyboard JSON.")
    parser.add_argument("--output", type=str, default="assets/frames/storyboard_grid.png", help="Output contact sheet path.")
    parser.add_argument("--cols", type=int, default=5, help="Number of columns in the grid.")
    parser.add_argument("--thumb-width", type=int, default=360, help="Thumbnail width in pixels.")
    parser.add_argument("--thumb-height", type=int, default=640, help="Thumbnail height in pixels.")

    args = parser.parse_args()

    create_contact_sheet(
        frames_dir=Path(args.frames_dir),
        storyboard_path=Path(args.storyboard),
        output_path=Path(args.output),
        thumb_width=args.thumb_width,
        thumb_height=args.thumb_height,
        cols=args.cols
    )


if __name__ == "__main__":
    main()
