import cv2
import subprocess
from pathlib import Path

from modules import shared
from modules.paths import data_path
from modules.processing import StableDiffusionProcessing

from scripts.animatediff_logger import logger_animatediff as logger


def get_animatediff_arg(p: StableDiffusionProcessing):
    """
    Get AnimateDiff argument from `p`. If it's a dict, convert it to AnimateDiffProcess.
    """
    if not p.scripts:
        return None

    for script in p.scripts.alwayson_scripts:
        if script.title().lower() == "animatediff":
            animatediff_arg = p.script_args[script.args_from]
            if isinstance(animatediff_arg, dict):
                from scripts.animatediff_ui import AnimateDiffProcess
                animatediff_arg = AnimateDiffProcess(**animatediff_arg)
                p.script_args[script.args_from] = animatediff_arg
            return animatediff_arg

    return None

def get_controlnet_units(p: StableDiffusionProcessing):
    """
    Get controlnet arguments from `p`.
    """
    if not p.scripts:
        return None

    for script in p.scripts.alwayson_scripts:
        if script.title().lower() == "controlnet":
            cn_units = p.script_args[script.args_from:script.args_to]
            return [x for x in cn_units if x.enabled]

    return None


def ffmpeg_extract_frames(source_video: str, output_dir: str, extract_key: bool = False):
    from modules.devices import device
    command = ["ffmpeg"]
    if "cuda" in str(device):
        command.extend(["-hwaccel", "cuda"])
    command.extend(["-i", source_video])
    if extract_key:
        command.extend(["-vf", "select='eq(pict_type,I)'", "-vsync", "vfr"])
    else:
        command.extend(["-filter:v", "mpdecimate=hi=64*200:lo=64*50:frac=0.33,setpts=N/FRAME_RATE/TB"])
    tmp_frame_dir = Path(output_dir)
    tmp_frame_dir.mkdir(parents=True, exist_ok=True)
    command.extend(["-qscale:v", "1", "-qmin", "1", "-c:a", "copy", str(tmp_frame_dir / '%09d.jpg')])
    logger.info(f"Attempting to extract frames via ffmpeg from {source_video} to {output_dir}")
    subprocess.run(command, check=True)


def cv2_extract_frames(source_video: str, output_dir: str):
    logger.info(f"Attempting to extract frames via OpenCV from {source_video} to {output_dir}")
    cap = cv2.VideoCapture(source_video)
    frame_count = 0
    tmp_frame_dir = Path(output_dir)
    tmp_frame_dir.mkdir(parents=True, exist_ok=True)
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        cv2.imwrite(f"{tmp_frame_dir}/{frame_count}.png", frame)
        frame_count += 1
    cap.release()



def extract_frames_from_video(params):
    assert params.video_source, "You need to specify cond hint for ControlNet."
    params.video_path = shared.opts.data.get(
        "animatediff_frame_extract_path",
        f"{data_path}/tmp/animatediff-frames")
    params.video_path += f"{params.video_source}-{generate_random_hash()}"
    try:
        ffmpeg_extract_frames(params.video_source, params.video_path)
    except Exception as e:
        logger.error(f"[AnimateDiff] Error extracting frames via ffmpeg: {e}, fall back to OpenCV.")
        cv2_extract_frames(params.video_source, params.video_path)
