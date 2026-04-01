"""Tests for GcodeGoblin G-code post-processing."""

import hashlib
import sys
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Add parent dir so we can import the single-file module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gcodeGoblin import (
    detect_command,
    main,
    process_gcode,
    process_lines,
    process_zip_file,
    remove_extrusion,
)


# ---------------------------------------------------------------------------
# remove_extrusion
# ---------------------------------------------------------------------------


class TestRemoveExtrusion:
    def test_strips_E_from_G1(self):
        assert remove_extrusion("G1 X10 Y20 E1.234") == "G1 X10 Y20"

    def test_strips_E_from_G2(self):
        assert remove_extrusion("G2 X5 Y5 I2 J0 E0.5") == "G2 X5 Y5 I2 J0"

    def test_strips_E_from_G3(self):
        assert remove_extrusion("G3 X5 Y5 I2 J0 E0.5") == "G3 X5 Y5 I2 J0"

    def test_negative_E(self):
        assert remove_extrusion("G1 X10 E-0.8") == "G1 X10"

    def test_no_E_param(self):
        assert remove_extrusion("G1 X10 Y20 F3000") == "G1 X10 Y20 F3000"

    def test_passthrough_non_move(self):
        assert remove_extrusion("M104 S200") == "M104 S200"

    def test_passthrough_comment(self):
        assert remove_extrusion("; hello") == "; hello"

    def test_passthrough_empty(self):
        assert remove_extrusion("") == ""


# ---------------------------------------------------------------------------
# detect_command
# ---------------------------------------------------------------------------


class TestDetectCommand:
    def test_exact_match(self):
        assert detect_command("; START_COPY:", "; START_COPY: layer1")

    def test_case_insensitive(self):
        assert detect_command("; START_COPY:", "; start_copy: layer1")

    def test_ignores_spaces(self):
        assert detect_command("; START_COPY:", ";  START_COPY : layer1")

    def test_no_match(self):
        assert not detect_command("; START_COPY:", "G1 X10 Y20")

    def test_partial_no_match(self):
        assert not detect_command("; START_COPY:", "; STOP_COPY: layer1")


# ---------------------------------------------------------------------------
# process_lines – buffer copy/paste
# ---------------------------------------------------------------------------


class TestProcessLinesCopyPaste:
    def test_copy_and_paste(self):
        lines = [
            "G28",
            "; START_COPY: buf1",
            "G1 X10 E1.0",
            "G1 X20 E2.0",
            "; STOP_COPY: buf1",
            "; PASTE: buf1",
            "M84",
        ]
        out = process_lines(lines)
        text = "\n".join(out)
        assert "G1 X10 E1.0" in text
        assert "G1 X20 E2.0" in text
        assert "; pasting from buffer buf1" in text
        assert "; END OF PASTE BUFFER" in text

    def test_paste_unknown_buffer_ignored(self):
        lines = ["G28", "; PASTE: nonexistent", "M84"]
        out = process_lines(lines)
        text = "\n".join(out)
        assert "pasting" not in text

    def test_multiple_buffers(self):
        lines = [
            "; START_COPY: a",
            "line_a",
            "; STOP_COPY: a",
            "; START_COPY: b",
            "line_b",
            "; STOP_COPY: b",
            "; PASTE: b",
            "; PASTE: a",
        ]
        out = process_lines(lines)
        text = "\n".join(out)
        b_pos = text.index("pasting from buffer b")
        a_pos = text.index("pasting from buffer a")
        assert b_pos < a_pos


# ---------------------------------------------------------------------------
# process_lines – cut
# ---------------------------------------------------------------------------


class TestProcessLinesCut:
    def test_cut_removes_lines(self):
        lines = [
            "G28",
            "; START_CUT",
            "G1 X10",
            "G1 X20",
            "; STOP_CUT",
            "M84",
        ]
        out = process_lines(lines)
        text = "\n".join(out)
        assert "G28" in text
        assert "M84" in text
        assert "G1 X10" not in text
        assert "G1 X20" not in text
        assert "; CUT START" in text
        assert "; CUT STOPPED" in text


# ---------------------------------------------------------------------------
# process_lines – extrusion control
# ---------------------------------------------------------------------------


class TestProcessLinesExtrusion:
    def test_stop_extrude_strips_E(self):
        lines = [
            "G1 X10 E1.0",
            "; STOP_EXTRUDE: reason",
            "G1 X20 E2.0",
            "G1 X30 E3.0",
            "; START_EXTRUDE: reason",
            "G1 X40 E4.0",
        ]
        out = process_lines(lines)
        # Before STOP_EXTRUDE: E preserved
        assert "G1 X10 E1.0" in out
        # After STOP_EXTRUDE: E removed
        assert "G1 X20" in out
        assert "G1 X20 E2.0" not in out
        assert "G1 X30" in out
        assert "G1 X30 E3.0" not in out
        # After START_EXTRUDE: E preserved again
        assert "G1 X40 E4.0" in out


# ---------------------------------------------------------------------------
# process_lines – REMOVE_EXTRUSION on buffer
# ---------------------------------------------------------------------------


class TestProcessLinesRemoveExtrusion:
    def test_remove_extrusion_from_buffer(self):
        lines = [
            "; START_COPY: layer",
            "G1 X10 E1.0",
            "G1 X20 E2.0",
            "; STOP_COPY: layer",
            "; REMOVE_EXTRUSION: layer",
            "; PASTE: layer",
        ]
        out = process_lines(lines)
        text = "\n".join(out)
        # The pasted lines should have E stripped
        paste_start = text.index("; pasting from buffer layer")
        paste_end = text.index("; END OF PASTE BUFFER")
        pasted_section = text[paste_start:paste_end]
        assert "E1.0" not in pasted_section
        assert "E2.0" not in pasted_section
        assert "G1 X10" in pasted_section
        assert "G1 X20" in pasted_section


# ---------------------------------------------------------------------------
# process_gcode – file round-trip
# ---------------------------------------------------------------------------


class TestProcessGcode:
    def test_round_trip(self, tmp_path):
        src = tmp_path / "test.gcode"
        src.write_text("G28\n; START_CUT\nG1 X10\n; STOP_CUT\nM84\n")

        process_gcode(str(src))

        fixed = tmp_path / "test.fixed.gcode"
        assert fixed.exists()
        content = fixed.read_text()
        assert "G28" in content
        assert "M84" in content
        assert "G1 X10" not in content


# ---------------------------------------------------------------------------
# process_zip_file – 3mf round-trip via bambuuzle
# ---------------------------------------------------------------------------


def _build_test_3mf(path: Path, gcode: str) -> Path:
    """Create a minimal Bambu .gcode.3mf for testing."""
    from bambuuzle import BambuFile

    bf = BambuFile()
    bf.add_plate(gcode)
    bf.save(str(path))
    return path


class TestProcessZipFile:
    def test_round_trip(self, tmp_path):
        original_gcode = "G28\n; START_CUT\nG1 X10\n; STOP_CUT\nM84\n"
        src = _build_test_3mf(tmp_path / "test.gcode.3mf", original_gcode)

        process_zip_file(str(src))

        fixed = tmp_path / "test.gcode.fixed.3mf"
        assert fixed.exists()

        with zipfile.ZipFile(fixed, "r") as zf:
            gcode = zf.read("Metadata/plate_1.gcode").decode("utf-8")
            md5 = zf.read("Metadata/plate_1.gcode.md5").decode("utf-8")

        assert "G28" in gcode
        assert "M84" in gcode
        assert "G1 X10" not in gcode
        assert md5 == hashlib.md5(gcode.encode("utf-8")).hexdigest()

    def test_copy_paste_in_3mf(self, tmp_path):
        original = (
            "G28\n"
            "; START_COPY: layer\n"
            "G1 X10 E1.0\n"
            "; STOP_COPY: layer\n"
            "; PASTE: layer\n"
            "M84\n"
        )
        src = _build_test_3mf(tmp_path / "test.gcode.3mf", original)
        process_zip_file(str(src))

        fixed = tmp_path / "test.gcode.fixed.3mf"
        with zipfile.ZipFile(fixed, "r") as zf:
            gcode = zf.read("Metadata/plate_1.gcode").decode("utf-8")

        assert gcode.count("G1 X10 E1.0") >= 2  # original + pasted


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


class TestMain:
    def test_no_args_exits(self):
        with patch("sys.argv", ["gcodegoblin"]):
            with pytest.raises(SystemExit):
                main()

    def test_bad_extension_exits(self):
        with patch("sys.argv", ["gcodegoblin", "file.txt"]):
            with pytest.raises(SystemExit):
                main()

    def test_gcode_file(self, tmp_path):
        src = tmp_path / "test.gcode"
        src.write_text("G28\nM84\n")
        with patch("sys.argv", ["gcodegoblin", str(src)]):
            main()
        assert (tmp_path / "test.fixed.gcode").exists()

    def test_3mf_file(self, tmp_path):
        src = _build_test_3mf(tmp_path / "test.gcode.3mf", "G28\nM84\n")
        with patch("sys.argv", ["gcodegoblin", str(src)]):
            main()
        assert (tmp_path / "test.gcode.fixed.3mf").exists()
