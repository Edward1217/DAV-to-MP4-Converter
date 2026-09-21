import subprocess
import tempfile
from pathlib import Path
import sys

# Get ffmpeg path 
def get_ffmpeg_path():

    # Running inside PyInstaller
    if getattr(sys, "frozen", False):

        base_path = Path(
            sys._MEIPASS
        )

    # Running normally with Python
    else:

        base_path = Path(
            __file__
        ).resolve().parent

    ffmpeg_path = (
        base_path
        /
        "ffmpeg"
        /
        "ffmpeg.exe"
    )

    if not ffmpeg_path.exists():

        raise FileNotFoundError(
            f"FFmpeg not found: {ffmpeg_path}"
        )

    return ffmpeg_path
# ============================================================
# ANNEX-B START CODE
# ============================================================

def find_start_codes(data: bytes):

    results = []

    i = 0

    while i < len(data) - 4:

        if data[i:i + 4] == b"\x00\x00\x00\x01":

            results.append(
                (i, 4)
            )

            i += 4

        elif data[i:i + 3] == b"\x00\x00\x01":

            results.append(
                (i, 3)
            )

            i += 3

        else:

            i += 1

    return results


# ============================================================
# H264 NAL TYPE
# ============================================================

def get_h264_nal_type(
    header_byte
):

    return (
        header_byte
        &
        0x1F
    )


# ============================================================
# HEVC / H265 NAL TYPE
# ============================================================

def get_hevc_nal_type(
    header_byte
):

    return (
        header_byte >> 1
    ) & 0x3F


# ============================================================
# DETECT CODEC
# ============================================================

def detect_codec(
    data: bytes
):

    start_codes = find_start_codes(
        data
    )

    h264_sps = 0
    h264_pps = 0

    hevc_vps = 0
    hevc_sps = 0
    hevc_pps = 0


    for offset, start_len in start_codes:

        header_position = (
            offset +
            start_len
        )

        if header_position >= len(data):
            continue


        header = data[
            header_position
        ]


        # ============================================
        # H264
        # ============================================

        h264_type = (
            get_h264_nal_type(
                header
            )
        )


        if h264_type == 7:

            h264_sps += 1

        elif h264_type == 8:

            h264_pps += 1


        # ============================================
        # H265 / HEVC
        # ============================================

        hevc_type = (
            get_hevc_nal_type(
                header
            )
        )


        if hevc_type == 32:

            hevc_vps += 1

        elif hevc_type == 33:

            hevc_sps += 1

        elif hevc_type == 34:

            hevc_pps += 1


    # ========================================================
    # HEVC
    # ========================================================

    if (
        hevc_vps > 0
        and
        hevc_sps > 0
        and
        hevc_pps > 0
    ):

        return "hevc"


    # ========================================================
    # H264
    # ========================================================

    if (
        h264_sps > 0
        and
        h264_pps > 0
    ):

        return "h264"


    return None


# ============================================================
# PARSE H264
# ============================================================

def parse_h264_nals(
    data
):

    start_codes = find_start_codes(
        data
    )

    nals = []


    for index, (
        offset,
        start_len
    ) in enumerate(start_codes):

        header_position = (
            offset +
            start_len
        )


        if header_position >= len(data):
            continue


        if index + 1 < len(start_codes):

            end = (
                start_codes[
                    index + 1
                ][0]
            )

        else:

            end = len(data)


        header = data[
            header_position
        ]


        nal_type = (
            get_h264_nal_type(
                header
            )
        )


        if not (
            1 <= nal_type <= 23
        ):

            continue


        nals.append({

            "offset": offset,

            "end": end,

            "type": nal_type,

            "data": data[
                offset:end
            ]
        })


    return nals


# ============================================================
# PARSE HEVC
# ============================================================

def parse_hevc_nals(
    data
):

    start_codes = find_start_codes(
        data
    )

    nals = []


    for index, (
        offset,
        start_len
    ) in enumerate(start_codes):

        header_position = (
            offset +
            start_len
        )


        # HEVC NAL header = 2 bytes
        if (
            header_position + 1
            >= len(data)
        ):

            continue


        if index + 1 < len(start_codes):

            end = (
                start_codes[
                    index + 1
                ][0]
            )

        else:

            end = len(data)


        header = data[
            header_position
        ]


        nal_type = (
            get_hevc_nal_type(
                header
            )
        )


        if not (
            0 <= nal_type <= 63
        ):

            continue


        nals.append({

            "offset": offset,

            "end": end,

            "type": nal_type,

            "data": data[
                offset:end
            ]
        })


    return nals


# ============================================================
# FIND H264 VIDEO START
# ============================================================

def find_h264_start(
    nals
):

    for i, nal in enumerate(
        nals
    ):

        if nal["type"] != 7:
            continue


        # Look for PPS shortly after SPS
        for j in range(
            i + 1,
            min(
                i + 8,
                len(nals)
            )
        ):

            if (
                nals[j]["type"]
                == 8
            ):

                return i


    return None


# ============================================================
# FIND HEVC VIDEO START
# ============================================================

def find_hevc_start(
    nals
):

    for i, nal in enumerate(
        nals
    ):

        # VPS
        if nal["type"] != 32:
            continue


        found_sps = False
        found_pps = False


        for j in range(
            i + 1,
            min(
                i + 10,
                len(nals)
            )
        ):

            nal_type = (
                nals[j][
                    "type"
                ]
            )


            if nal_type == 33:

                found_sps = True


            elif nal_type == 34:

                found_pps = True


            if (
                found_sps
                and
                found_pps
            ):

                return i


    return None


# ============================================================
# EXTRACT VIDEO
# ============================================================

def extract_video(
    dav_file,
    video_file
):

    dav_file = Path(
        dav_file
    )

    video_file = Path(
        video_file
    )


    data = dav_file.read_bytes()


    codec = detect_codec(
        data
    )


    if codec is None:

        raise RuntimeError(
            "Unable to detect H.264 or H.265 video."
        )


    # ========================================================
    # H264
    # ========================================================

    if codec == "h264":

        nals = parse_h264_nals(
            data
        )


        start_index = (
            find_h264_start(
                nals
            )
        )


        if start_index is None:

            raise RuntimeError(
                "Cannot find valid H.264 SPS/PPS."
            )


    # ========================================================
    # H265
    # ========================================================

    elif codec == "hevc":

        nals = parse_hevc_nals(
            data
        )


        start_index = (
            find_hevc_start(
                nals
            )
        )


        if start_index is None:

            raise RuntimeError(
                "Cannot find valid HEVC VPS/SPS/PPS."
            )


    # ========================================================
    # WRITE VIDEO STREAM
    # ========================================================

    with open(
        video_file,
        "wb"
    ) as output:

        for nal in nals[
            start_index:
        ]:

            output.write(
                nal["data"]
            )


    return codec


# ============================================================
# CREATE MP4
# ============================================================

def create_mp4(
    video_file,
    output_file,
    codec,
    fps=30
):

    video_file = Path(
        video_file
    )

    output_file = Path(
        output_file
    )

    # ========================================================
    # GET FFMPEG PATH
    # ========================================================

    ffmpeg_path = get_ffmpeg_path()

    # ========================================================
    # INPUT FORMAT
    # ========================================================

    if codec == "h264":

        input_format = "h264"

    elif codec == "hevc":

        input_format = "hevc"

    else:

        raise RuntimeError(
            f"Unsupported codec: {codec}"
        )

    # ========================================================
    # FFMPEG COMMAND
    # ========================================================

    command = [

        str(ffmpeg_path),

        "-y",

        "-loglevel",
        "error",

        "-f",
        input_format,

        "-framerate",
        str(fps),

        "-i",
        str(video_file),

        "-c:v",
        "copy",

        "-movflags",
        "+faststart",

        str(output_file)
    ]

    # ========================================================
    # RUN FFMPEG
    # ========================================================

    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:

        raise RuntimeError(
            result.stderr
            or
            "FFmpeg conversion failed."
        )


# ============================================================
# DAV -> MP4
# ============================================================

def dav_to_mp4(
    input_file,
    output_file,
    fps=30
):

    input_path = Path(
        input_file
    )

    output_path = Path(
        output_file
    )


    if not input_path.exists():

        raise FileNotFoundError(
            f"File not found: {input_path}"
        )


    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )


    # ========================================================
    # TEMP DIRECTORY
    # ========================================================

    with tempfile.TemporaryDirectory() as temp_dir:

        temp_dir = Path(
            temp_dir
        )


        # Read once for codec detection
        data = input_path.read_bytes()

        codec = detect_codec(
            data
        )


        if codec == "h264":

            video_file = (
                temp_dir /
                "video.h264"
            )


        elif codec == "hevc":

            video_file = (
                temp_dir /
                "video.h265"
            )


        else:

            raise RuntimeError(
                "Unsupported or unknown DAV video codec."
            )


        # ================================================
        # EXTRACT
        # ================================================

        codec = extract_video(
            input_path,
            video_file
        )


        # ================================================
        # MP4
        # ================================================

        create_mp4(
            video_file,
            output_path,
            codec,
            fps
        )


    return output_path