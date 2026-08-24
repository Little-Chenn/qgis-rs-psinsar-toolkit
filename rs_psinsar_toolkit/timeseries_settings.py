"""Settings, read-only input inspection, and point selection for time-series review."""

from __future__ import annotations

import csv
import math
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .localization import tr


_TR_CONTEXT = "@default"


def _tr(source: str) -> str:
    return tr(_TR_CONTEXT, source)


DATE_FIELD_PREFIX = "D_"
TARGET_STRATA = (
    ("A_CLUSTER", "LOW"),
    ("A_CLUSTER", "HIGH"),
    ("B_ISOLATED", "LOW"),
    ("B_ISOLATED", "HIGH"),
)
MAX_SELECTED_POINTS = 200


@dataclass(frozen=True)
class TimeSeriesField:
    ordinal: int
    field_name: str
    acquisition_date: str
    unit: str
    is_initial: bool


@dataclass(frozen=True)
class TimeSeriesSettings:
    input_gpkg: str
    point_csv: str
    output_root: str
    quota_per_stratum: int = 12
    minimum_distance_m: float = 500.0
    export_csv: bool = True
    export_gpkg: bool = True
    export_png: bool = True
    export_pdf: bool = True
    load_result: bool = True


@dataclass(frozen=True)
class InputInspection:
    fields: tuple[TimeSeriesField, ...]
    point_mode: str
    source_row_count: int
    selected_point_count: int
    selection: tuple[dict[str, Any], ...]


class TimeSeriesInputError(ValueError):
    """Raised when an input cannot be used safely."""


def _readonly_connection(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)


def read_time_catalog(path: str | Path) -> tuple[TimeSeriesField, ...]:
    gpkg = Path(path).expanduser().resolve()
    if not gpkg.is_file():
        raise TimeSeriesInputError(
            _tr("多时相 GeoPackage 不存在：{path}").format(path=gpkg)
        )
    try:
        with closing(_readonly_connection(gpkg)) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            required = {"ps_timeseries_points", "time_catalog"}
            missing = required - tables
            if missing:
                raise TimeSeriesInputError(
                    _tr("GeoPackage 缺少必需表：{tables}").format(
                        tables=", ".join(sorted(missing))
                    )
                )
            rows = connection.execute(
                "SELECT ordinal, field_name, acquisition_date, "
                "displacement_unit, is_initial "
                "FROM time_catalog ORDER BY ordinal"
            ).fetchall()
            point_fields = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(ps_timeseries_points)"
                )
            }
    except sqlite3.Error as exc:
        raise TimeSeriesInputError(
            _tr("无法只读检查 GeoPackage：{error}").format(error=exc)
        ) from exc
    if not rows:
        raise TimeSeriesInputError(_tr("time_catalog 为空。"))
    result = tuple(
        TimeSeriesField(
            ordinal=int(row[0]),
            field_name=str(row[1]),
            acquisition_date=str(row[2]),
            unit=str(row[3]),
            is_initial=bool(row[4]),
        )
        for row in rows
    )
    if sum(item.is_initial for item in result) != 1:
        raise TimeSeriesInputError(
            _tr("time_catalog 必须且只能包含一个初始时相。")
        )
    if any(item.unit != "mm" for item in result):
        raise TimeSeriesInputError(
            _tr("时相单位不是统一的 mm，已拒绝自动换算。")
        )
    if any(item.field_name not in point_fields for item in result):
        raise TimeSeriesInputError(
            _tr("时相目录与 ps_timeseries_points 字段不一致。")
        )
    for item in result:
        try:
            datetime.strptime(item.acquisition_date, "%Y-%m-%d")
        except ValueError as exc:
            raise TimeSeriesInputError(
                _tr("无效观测日期：{date}").format(
                    date=item.acquisition_date
                )
            ) from exc
    return result


def _number(row: dict[str, str], *names: str, default: float = 0.0) -> float:
    for name in names:
        value = row.get(name, "").strip()
        if value:
            return float(value)
    return default


def _integer(row: dict[str, str], *names: str, default: int = 0) -> int:
    return int(_number(row, *names, default=float(default)))


def read_point_rows(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise TimeSeriesInputError(
            _tr("点位 CSV 不存在：{path}").format(path=source)
        )
    rows: list[dict[str, Any]] = []
    try:
        with source.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            fields = set(reader.fieldnames or ())
            if "ps_uid" not in fields:
                raise TimeSeriesInputError(
                    _tr("点位 CSV 至少需要 ps_uid 字段。")
                )
            for index, raw in enumerate(reader, start=1):
                uid = _integer(raw, "ps_uid")
                if uid <= 0:
                    raise TimeSeriesInputError(
                        _tr("第 {index} 行 ps_uid 无效。").format(
                            index=index
                        )
                    )
                rows.append(
                    {
                        "selection_rank": _integer(
                            raw, "selection_rank", default=index
                        ),
                        "stratum_rank": _integer(
                            raw, "stratum_rank", default=index
                        ),
                        "ps_uid": uid,
                        "review_tier": raw.get("review_tier", "USER_SELECTED").strip()
                        or "USER_SELECTED",
                        "tail_side": raw.get("tail_side", "UNSPECIFIED").strip()
                        or "UNSPECIFIED",
                        "velocity_mm_per_year": _number(
                            raw, "velocity_mm_per_year", "velocity"
                        ),
                        "coherence": _number(raw, "coherence"),
                        "local_rz": _number(raw, "local_rz"),
                        "support_n": _integer(raw, "support_n"),
                        "lon": _number(raw, "lon"),
                        "lat": _number(raw, "lat"),
                        "has_explicit_rank": "selection_rank" in fields,
                        "has_candidate_fields": {
                            "review_tier",
                            "tail_side",
                            "local_rz",
                            "support_n",
                        }.issubset(fields),
                    }
                )
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        if isinstance(exc, TimeSeriesInputError):
            raise
        raise TimeSeriesInputError(
            _tr("无法读取点位 CSV：{error}").format(error=exc)
        ) from exc
    if not rows:
        raise TimeSeriesInputError(_tr("点位 CSV 没有数据行。"))
    if len({row["ps_uid"] for row in rows}) != len(rows):
        raise TimeSeriesInputError(_tr("点位 CSV 中 ps_uid 重复。"))
    return rows


def haversine_m(left: dict[str, Any], right: dict[str, Any]) -> float:
    radius = 6_371_008.8
    lat1 = math.radians(float(left["lat"]))
    lat2 = math.radians(float(right["lat"]))
    dlat = lat2 - lat1
    dlon = math.radians(float(right["lon"]) - float(left["lon"]))
    value = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    )
    return 2.0 * radius * math.asin(min(1.0, math.sqrt(value)))


def _candidate_key(row: dict[str, Any]) -> tuple[float, ...]:
    if row["review_tier"] == "A_CLUSTER":
        return (
            -float(row["support_n"]),
            -abs(float(row["velocity_mm_per_year"])),
            -float(row["coherence"]),
            float(row["ps_uid"]),
        )
    return (
        -abs(float(row["local_rz"])),
        -abs(float(row["velocity_mm_per_year"])),
        -float(row["coherence"]),
        float(row["ps_uid"]),
    )


def controlled_sample(
    rows: list[dict[str, Any]],
    quota_per_stratum: int,
    minimum_distance_m: float,
) -> list[dict[str, Any]]:
    pools = {
        stratum: sorted(
            [
                row
                for row in rows
                if (row["review_tier"], row["tail_side"]) == stratum
            ],
            key=_candidate_key,
        )
        for stratum in TARGET_STRATA
    }
    selected: list[dict[str, Any]] = []
    counts = {stratum: 0 for stratum in TARGET_STRATA}
    indices = {stratum: 0 for stratum in TARGET_STRATA}
    round_index = 0
    while any(counts[item] < quota_per_stratum for item in TARGET_STRATA):
        progress = False
        offset = round_index % len(TARGET_STRATA)
        order = TARGET_STRATA[offset:] + TARGET_STRATA[:offset]
        for stratum in order:
            if counts[stratum] >= quota_per_stratum:
                continue
            pool = pools[stratum]
            while indices[stratum] < len(pool):
                row = pool[indices[stratum]]
                indices[stratum] += 1
                if all(
                    haversine_m(row, existing) >= minimum_distance_m
                    for existing in selected
                ):
                    selected.append(dict(row))
                    counts[stratum] += 1
                    progress = True
                    break
        if not progress:
            break
        round_index += 1
    if any(counts[item] != quota_per_stratum for item in TARGET_STRATA):
        detail = ", ".join(
            f"{tier}/{side}={counts[(tier, side)]}"
            for tier, side in TARGET_STRATA
        )
        raise TimeSeriesInputError(
            _tr("在当前最小间距下无法满足四层配额：{detail}").format(
                detail=detail
            )
        )
    stratum_counts = {stratum: 0 for stratum in TARGET_STRATA}
    for rank, row in enumerate(selected, start=1):
        stratum = (row["review_tier"], row["tail_side"])
        stratum_counts[stratum] += 1
        row["selection_rank"] = rank
        row["stratum_rank"] = stratum_counts[stratum]
    return selected


def inspect_inputs(settings: TimeSeriesSettings) -> InputInspection:
    fields = read_time_catalog(settings.input_gpkg)
    rows = read_point_rows(settings.point_csv)
    explicit = all(row["has_explicit_rank"] for row in rows)
    candidates = all(row["has_candidate_fields"] for row in rows)
    if explicit:
        selected = sorted(rows, key=lambda row: row["selection_rank"])
        mode = "点位清单原样回查"
    elif candidates:
        selected = controlled_sample(
            rows,
            settings.quota_per_stratum,
            settings.minimum_distance_m,
        )
        mode = "A/B×LOW/HIGH 受控抽样"
    else:
        selected = rows
        for rank, row in enumerate(selected, start=1):
            row["selection_rank"] = rank
            row["stratum_rank"] = rank
        mode = "ps_uid 清单原样回查"
    if len(selected) > MAX_SELECTED_POINTS:
        raise TimeSeriesInputError(
            _tr(
                "本版单次最多回查 {maximum} 点；当前为 {count} 点。"
            ).format(maximum=MAX_SELECTED_POINTS, count=len(selected))
        )
    return InputInspection(
        fields=fields,
        point_mode=mode,
        source_row_count=len(rows),
        selected_point_count=len(selected),
        selection=tuple(selected),
    )


def validate_settings(settings: TimeSeriesSettings) -> list[str]:
    errors: list[str] = []
    if not Path(settings.output_root).expanduser().is_dir():
        errors.append(_tr("输出根目录不存在。"))
    if not 1 <= settings.quota_per_stratum <= 50:
        errors.append(_tr("每层点数必须在 1–50 之间。"))
    if not 0.0 <= settings.minimum_distance_m <= 100_000.0:
        errors.append(_tr("最小空间间距必须在 0–100000 m 之间。"))
    if not any(
        (
            settings.export_csv,
            settings.export_gpkg,
            settings.export_png,
            settings.export_pdf,
        )
    ):
        errors.append(_tr("至少选择一种输出格式。"))
    if not errors:
        try:
            inspect_inputs(settings)
        except (OSError, sqlite3.Error, TimeSeriesInputError) as exc:
            errors.append(str(exc))
    return errors


def localized_point_mode(mode: str) -> str:
    """Translate a display label without changing the stored selection mode."""
    labels = {
        "点位清单原样回查": _tr("点位清单原样回查"),
        "A/B×LOW/HIGH 受控抽样": _tr("A/B×LOW/HIGH 受控抽样"),
        "ps_uid 清单原样回查": _tr("ps_uid 清单原样回查"),
    }
    return labels.get(mode, mode)
