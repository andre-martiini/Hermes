"""Reparos conservadores para contêineres MP4/M4A parcialmente truncados."""

from __future__ import annotations

import os
import struct


def repair_truncated_stsz(source_path: str, output_path: str) -> dict | None:
    """Reduz sample_count de caixas STSZ ao número de entradas ainda presentes.

    Alguns gravadores Samsung deixam o ``mdat`` intacto, mas truncam o final da
    tabela STSZ. O FFmpeg então descarta toda a tabela e produz zero quadros. Esta
    função só altera uma cópia e nunca inventa entradas: mantém apenas os tamanhos
    de amostra que realmente existem no arquivo.
    """
    with open(source_path, "rb") as source:
        data = bytearray(source.read())

    repairs = []
    search_from = 0
    while True:
        marker = data.find(b"stsz", search_from)
        if marker < 0:
            break
        search_from = marker + 4
        box_start = marker - 4
        if box_start < 0 or marker + 16 > len(data):
            continue

        box_size = struct.unpack_from(">I", data, box_start)[0]
        version_flags = struct.unpack_from(">I", data, marker + 4)[0]
        sample_size = struct.unpack_from(">I", data, marker + 8)[0]
        declared_count = struct.unpack_from(">I", data, marker + 12)[0]
        if (
            box_size < 20
            or version_flags >> 24 != 0
            or sample_size != 0
            or declared_count == 0
        ):
            continue

        entries_start = marker + 16
        declared_end = box_start + box_size
        available_end = min(declared_end, len(data))
        available_count = max(0, (available_end - entries_start) // 4)
        if available_count >= declared_count:
            continue

        struct.pack_into(">I", data, marker + 12, available_count)
        if declared_end > len(data):
            struct.pack_into(">I", data, box_start, len(data) - box_start)
        repairs.append({
            "offset": box_start,
            "declaredSamples": declared_count,
            "availableSamples": available_count,
            "declaredBoxBytes": box_size,
            "availableBoxBytes": available_end - box_start,
        })

    if not repairs or not any(item["availableSamples"] > 0 for item in repairs):
        return None

    with open(output_path, "wb") as output:
        output.write(data)
    return {
        "sourceBytes": os.path.getsize(source_path),
        "outputBytes": os.path.getsize(output_path),
        "repairs": repairs,
    }
