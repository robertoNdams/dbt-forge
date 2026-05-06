"""Tests for the dbt-stdout block parser."""

from __future__ import annotations

from pathlib import Path

from dbt_forge_cli.runner import _parse_emitted_blocks


def test_parses_single_file_block():
    stdout = (
        "some dbt log line\n"
        '<<<DBT_FORGE_FILE path="models/generated/foo.sql">>>\n'
        "{{ config(materialized='view') }}\n"
        "\n"
        "select * from x\n"
        "<<<DBT_FORGE_END>>>\n"
        "another log line\n"
    )
    blocks = _parse_emitted_blocks(stdout)
    assert len(blocks) == 1
    b = blocks[0]
    assert b.kind == "FILE"
    assert b.path == Path("models/generated/foo.sql")
    assert b.body.startswith("{{ config(materialized='view') }}")
    assert b.body.endswith("select * from x")


def test_parses_multiple_blocks_in_order():
    stdout = (
        '<<<DBT_FORGE_FILE path="a.sql">>>\nA\n<<<DBT_FORGE_END>>>\n'
        "noise\n"
        '<<<DBT_FORGE_FILE path="b.sql">>>\nB1\nB2\n<<<DBT_FORGE_END>>>\n'
    )
    blocks = _parse_emitted_blocks(stdout)
    assert [b.path.name for b in blocks] == ["a.sql", "b.sql"]
    assert blocks[1].body == "B1\nB2"


def test_parses_dryrun_blocks():
    stdout = '<<<DBT_FORGE_DRYRUN path="x.sql">>>\nhello\n<<<DBT_FORGE_END>>>\n'
    blocks = _parse_emitted_blocks(stdout)
    assert blocks[0].kind == "DRYRUN"


def test_ignores_non_matching_text():
    stdout = "no markers here at all\n"
    assert _parse_emitted_blocks(stdout) == []
