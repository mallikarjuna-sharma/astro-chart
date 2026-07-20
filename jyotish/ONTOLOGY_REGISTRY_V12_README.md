# JyotishAI Ontology + Registry v12 Upgrade

This package fixes the ontology/registry gaps identified in the audit without changing your deterministic astrological scoring formula.

## Files to add

Copy these files into your `jyotish/` package:

```text
jyotish/registry_v12_schema.py
jyotish/registry_v12_builder.py
jyotish/registry_coverage_validator.py
jyotish/registry_loader_v12.py
jyotish/report_utils.py
jyotish/india_course_registry_v12.json
```

## Build / refresh the v12 registry

From project root:

```bash
python -m jyotish.registry_v12_builder \
  --input jyotish/india_course_registry_v11.json \
  --output jyotish/india_course_registry_v12.json
```

## Validate coverage

```bash
python -m jyotish.registry_coverage_validator \
  --registry jyotish/india_course_registry_v12.json
```

Expected result:

```json
{
  "ok": true,
  "counts": {"registry": 199, "affinity": 199, "ontology": 199}
}
```

## Patch `engine_io.py`

Replace the current `_load_course_registry()` with:

```python
def _load_course_registry() -> Dict[str, Dict]:
    """Load v12 registry when available; fail if registry is empty."""
    try:
        from .registry_loader_v12 import load_course_registry_v12
        return load_course_registry_v12(prefer_v12=True, validate=True)
    except Exception as exc:
        logger.warning("v12 registry loader failed, falling back to v11 legacy loader: %s", exc)

    _dir = os.path.dirname(os.path.abspath(__file__))
    _path = os.path.join(_dir, "india_course_registry_v11.json")
    with open(_path, "rb") as _f:
        _raw = _f.read().replace(b"\x00", b"").replace(b"\r", b"")
    _data = json.loads(_raw)
    branches = _data.get("branches", {})
    if not branches:
        raise RuntimeError(f"Course registry loaded empty: {_path}")
    for _ext in (SPACE_AEROSPACE_REGISTRY_EXTENSIONS, LIFE_SCIENCE_REGISTRY_EXTENSIONS):
        for _fid, _emeta in _ext.items():
            if _fid in branches:
                for _k, _v in _emeta.items():
                    branches[_fid].setdefault(_k, _v)
            else:
                branches[_fid] = dict(_emeta)
    return branches
```

## Patch `career_field_report_v2.py`

Replace internal imports from `field_deterministic_engine_v1_llm` for display helpers with:

```python
from .report_utils import field_display_name as _field_display_name
from .report_utils import print_macro_cluster as _print_macro_cluster
from .report_utils import top20_as_four_cluster_groups as _top20_as_four_cluster_groups
```

Then update any function using the old local helpers to call the shared helpers. This removes the report -> CLI shim dependency.

## Patch CLI shim optionally

In `field_deterministic_engine_v1_llm.py`, you can replace the duplicated helper implementations with:

```python
from jyotish.report_utils import (
    field_display_name as _field_display_name,
    print_macro_cluster as _print_macro_cluster,
    cluster_display_name as _cluster_display_name,
    top20_as_four_cluster_groups as _top20_as_four_cluster_groups,
)
```

## What v12 adds to every branch

Each branch now has:

```text
classic_core
modern_extensions
admission_exams_canonical
available_at_normalized
ontology
education_realism
curriculum
market
risk
routes
career_outcomes
schema_version
```

The original v11 keys are preserved, so current engine code remains backward compatible.
