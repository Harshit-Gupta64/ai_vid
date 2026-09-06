import os, sys, json, subprocess, math
from PIL import Image

def run_ffprobe(cmd):
    res = subprocess.run(cmd, capture_output=True, text=True)
    return res.stdout.strip()

def audit(video_path, storyboard_path):
    print(f"[*] Auditing: {video_path}")
    if not os.path.exists(video_path) or os.path.getsize(video_path) < 100_000:
        sys.exit("FAIL: Video file missing or smaller than 100KB (corrupt/empty).")

    with open(storyboard_path, "r") as f:
        sb = json.load(f)

    # 1. Container & Streams Check
    probe_cmd = ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,pix_fmt,width,height", "-of", "json", video_path]
    probe_data = json.loads(run_ffprobe(probe_cmd))
    streams = {s["codec_type"]: s for s in probe_data.get("streams", [])}

    if "video" not in streams or "audio" not in streams:
        sys.exit("FAIL: Missing video or audio stream.")
    v, a = streams["video"], streams["audio"]

    if v["width"] != 1080 or v["height"] != 1920:
        sys.exit(f"FAIL: Resolution mismatch. Expected 1080x1920, got {v['width']}x{v['height']}.")
    if v["pix_fmt"] != "yuv420p":
        sys.exit(f"FAIL: pix_fmt is {v['pix_fmt']}. Must be yuv420p for OS player support.")

    # 2. Frame-Delta Analysis (Anti-Freeze Verification)
    scenes = sb["scenes"]
    extracted_frames = []
    os.makedirs("temp_qa", exist_ok=True)
    
    current_time = 0.0
    for idx, scene in enumerate(scenes):
        duration = float(scene.get("target_duration", 5.0))
        sample_time = current_time + (duration / 2.0)
        out_frame = f"temp_qa/frame_{idx}.png"
        subprocess.run(["ffmpeg", "-y", "-ss", str(sample_time), "-i", video_path, "-vframes", "1", out_frame], capture_output=True)
        extracted_frames.append(out_frame)
        current_time += duration

    # Compare Scene 0 to Scene 1 to ensure cut occurred
    if len(extracted_frames) >= 2:
        img1 = Image.open(extracted_frames[0]).convert('L').resize((64, 64))
        img2 = Image.open(extracted_frames[1]).convert('L').resize((64, 64))
        diff = sum(abs(p1 - p2) for p1, p2 in zip(img1.getdata(), img2.getdata())) / 4096.0
        if diff < 2.0:
            sys.exit(f"FAIL: Scene 1 and Scene 2 frames are visually identical (diff={diff:.2f}). Pipeline is frozen on a single image.")

    # 3. Audio Energy Metering
    vol_cmd = ["ffmpeg", "-i", video_path, "-af", "volumedetect", "-vn", "-sn", "-dn", "-f", "null", "NUL" if os.name == 'nt' else "/dev/null"]
    vol_out = subprocess.run(vol_cmd, capture_output=True, text=True).stderr
    for line in vol_out.splitlines():
        if "mean_volume:" in line:
            mean_vol = float(line.split("mean_volume:")[1].split("dB")[0].strip())
            if mean_vol < -38.0:
                sys.exit(f"FAIL: Video is virtually silent (mean_volume: {mean_vol} dB). Voiceover dropped.")

    print("PASS: Codec, Multi-Scene Frame Variance, and Audio Levels verified.")

if __name__ == "__main__":
    audit(sys.argv[1], sys.argv[2])