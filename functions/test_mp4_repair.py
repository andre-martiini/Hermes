import struct
import subprocess
import wave

import imageio_ffmpeg

from mp4_repair import repair_truncated_stsz


def test_repair_truncated_stsz(tmp_path):
    source = tmp_path / "broken.m4a"
    output = tmp_path / "repaired.m4a"
    # STSZ declara três amostras, mas só contém duas entradas.
    box = struct.pack(">I4sIII", 32, b"stsz", 0, 0, 3) + struct.pack(">II", 100, 120)
    source.write_bytes(box)

    result = repair_truncated_stsz(str(source), str(output))

    assert result is not None
    repaired = output.read_bytes()
    assert struct.unpack_from(">I", repaired, 16)[0] == 2
    assert result["repairs"][0]["declaredSamples"] == 3
    assert result["repairs"][0]["availableSamples"] == 2


def test_repaired_real_m4a_can_be_decoded(tmp_path):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    original = tmp_path / "original.m4a"
    broken = tmp_path / "broken.m4a"
    repaired = tmp_path / "repaired.m4a"
    decoded = tmp_path / "decoded.wav"

    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-c:a",
            "aac",
            str(original),
        ],
        check=True,
        capture_output=True,
    )
    corrupted_data = bytearray(original.read_bytes())
    marker = corrupted_data.find(b"stsz")
    assert marker >= 0
    original_count = struct.unpack_from(">I", corrupted_data, marker + 12)[0]
    struct.pack_into(">I", corrupted_data, marker + 12, original_count + 1)
    broken.write_bytes(corrupted_data)

    result = repair_truncated_stsz(str(broken), str(repaired))
    assert result is not None
    assert result["repairs"][0]["availableSamples"] == original_count

    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(repaired),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(decoded),
        ],
        check=True,
        capture_output=True,
    )
    with wave.open(str(decoded), "rb") as decoded_wave:
        assert decoded_wave.getnframes() > 0
