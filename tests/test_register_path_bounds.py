"""Reading a register back is bounded, and writing one back only touches a register.

Two defects on the same path — the documented workflow where an operator exports a register, a
reviewer edits it, and the operator applies it back.

**T23 — no decompression bounds.** `read_rows` and `write_back` call
`openpyxl.load_workbook` on a caller-supplied path with no size caps, while `_cellmap.py` applies
header-checked member, total and count bounds to *the same archive class*. Two parsers of `.xlsx`
in one codebase with opposite postures.

Reduced during the audit, and worth restating so the fix is not oversold: **XXE and entity
expansion are already covered** — openpyxl auto-detects `defusedxml` (env `OPENPYXL_DEFUSEDXML`,
default on) and `defusedxml` is a hard dependency here. What remains is **decompression
amplification**: a few-KB `.xlsx` that expands to gigabytes. A denial of service, not a
disclosure.

The bounds are read from the **zip central directory** rather than by decompressing and
measuring, which is the only way a cap can help: `zinfo.file_size` is the declared uncompressed
size, so a bomb is refused before any of it is expanded. That is the same technique `_cellmap.py`
already uses, which is the point — one archive class should not have two postures.

**T13 — write-back had none of the export path's inertness.** `resolve_export_path` is careful
about a model-supplied path in three ways; `write_back` rewrites one with none of them.

The proportionate half is fixed here: **the suffix is enforced**, so a register can only be
written back over a `.csv` or `.xlsx`. The rest is deliberately *not* copied, and the reasons
are worth recording rather than leaving as an apparent omission:

  * *never-overwrite* cannot apply — overwriting the register in place is the entire job, and
    `-<stamp>`-ing it would leave the completed markers in a file nobody re-applies;
  * *`export_dir` confinement* would break the documented flow, since a reviewer may hand the
    file back from anywhere;
  * *the temp file in `path.parent`* is **required**, not an oversight: an atomic rename needs
    the temp file on the same filesystem as the target.

What genuinely bounds this path is unchanged and is stronger than a path rule: `read_rows` must
parse the file as a register first, so a path that is not already one is refused before anything
is written.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import openpyxl
import pytest

from csa_google_workspace import _apply


def a_real_register(path: Path) -> Path:
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["thread_id", "reply_comment", "reply_comment_completed"])
    ws.append(["t1", "", ""])
    wb.save(path)
    return path


def a_zip_bomb(path: Path, declared: int) -> Path:
    """An archive whose central directory DECLARES a huge member.

    Deliberately declared rather than genuinely huge: the point of checking `file_size` is that
    a cap works without expanding anything, and a test that had to write a real gigabyte would
    be proving something else.
    """
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/worksheets/sheet1.xml", b"<x/>" * 8)
        # Rewrite the header's uncompressed size to the claimed value.
        for info in z.infolist():
            info.file_size = declared
    # zipfile writes sizes on close, so patch the finished file's central directory instead.
    raw = bytearray(path.read_bytes())
    return _patch_declared_size(path, raw, declared)


def _patch_declared_size(path: Path, raw: bytearray, declared: int) -> Path:
    """Overwrite every uncompressed-size field with `declared`."""
    for sig, offset in ((b"PK\x03\x04", 22), (b"PK\x01\x02", 24)):
        start = 0
        while (i := raw.find(sig, start)) != -1:
            raw[i + offset:i + offset + 4] = declared.to_bytes(4, "little")
            start = i + 4
    path.write_bytes(bytes(raw))
    return path


class TestReadingARegisterIsBounded:
    def test_an_archive_declaring_a_huge_member_is_refused(self, tmp_path):
        path = a_zip_bomb(tmp_path / "r.xlsx", declared=_apply.MAX_REGISTER_UNCOMPRESSED + 1)
        with pytest.raises(ValueError, match="(?i)limit|refusing"):
            _apply.read_rows(path)

    def test_the_refusal_names_the_cap(self, tmp_path):
        path = a_zip_bomb(tmp_path / "r.xlsx", declared=_apply.MAX_REGISTER_UNCOMPRESSED + 1)
        with pytest.raises(ValueError) as e:
            _apply.read_rows(path)
        assert "MiB" in str(e.value) or "MB" in str(e.value), (
            "a size refusal has to say what the size limit is, or it is unactionable")

    def test_nothing_is_decompressed_to_find_out(self, tmp_path):
        """The bomb declares gigabytes and the file is a few hundred bytes. If the check needed
        to expand it to decide, this test would not finish."""
        # 4 GiB - 1: the largest a zip's 32-bit uncompressed-size field can express, which is
        # why the bomb declares that rather than something rounder. ZIP64 could say more; the
        # cap is far below either.
        path = a_zip_bomb(tmp_path / "r.xlsx", declared=0xFFFFFFFF)
        assert path.stat().st_size < 5000
        with pytest.raises(ValueError):
            _apply.read_rows(path)

    def test_a_normal_register_still_reads(self, tmp_path):
        rows = _apply.read_rows(a_real_register(tmp_path / "r.xlsx"))
        assert rows and rows[0]["thread_id"] == "t1"

    def test_a_csv_register_is_unaffected(self, tmp_path):
        path = tmp_path / "r.csv"
        path.write_text("thread_id,reply_comment\nt1,\n", encoding="utf-8")
        assert _apply.read_rows(path)[0]["thread_id"] == "t1"

    def test_writing_back_is_bounded_too(self, tmp_path):
        """`write_back` re-opens the workbook, so the same cap has to apply there or the bound
        is only on one of the two parses."""
        path = a_zip_bomb(tmp_path / "r.xlsx", declared=_apply.MAX_REGISTER_UNCOMPRESSED + 1)
        with pytest.raises(ValueError):
            _apply.write_back(path, [{"thread_id": "t1"}], ["thread_id"])


class TestWritingBackOnlyTouchesARegister:
    def test_a_foreign_suffix_is_refused(self, tmp_path):
        path = tmp_path / "notes.txt"
        path.write_text("thread_id,reply_comment\nt1,\n", encoding="utf-8")
        with pytest.raises(ValueError, match="(?i)csv|xlsx"):
            _apply.write_back(path, [{"thread_id": "t1"}], ["thread_id"])

    @pytest.mark.parametrize("name", ["r.csv", "r.CSV", "r.xlsx", "r.XLSX"])
    def test_the_two_real_suffixes_are_accepted_either_case(self, tmp_path, name):
        path = tmp_path / name
        if path.suffix.lower() == ".xlsx":
            a_real_register(path)
        else:
            path.write_text("thread_id,reply_comment_completed\nt1,\n", encoding="utf-8")
        _apply.write_back(path, [{"thread_id": "t1", "reply_comment_completed": "yes"}],
                          ["thread_id", "reply_comment_completed"])
        assert path.exists()

    def test_the_original_bound_still_holds(self, tmp_path):
        """What actually protects this path, and it is stronger than a suffix rule: a file that
        is not already a register cannot be applied, so it is never reached for writing."""
        path = tmp_path / "notes.csv"
        path.write_text("not,a,register\n1,2,3\n", encoding="utf-8")
        rows = _apply.read_rows(path)
        assert "thread_id" not in (rows[0] if rows else {}), (
            "precondition: this file does not carry a register's columns")
