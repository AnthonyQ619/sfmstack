"""SceneDescription -- scene/v1 -> scene_analysis/v1. CPU, no model.

The odd one out. Every other module in this repository computes its output; this
one renders something to look at, and then stores what a viewer said about it.
The looking happens outside the container and there is no way for the module to
verify it -- which is exactly why the report is validated for SHAPE here and
marked as asserted rather than measured in the schema.

Two calls, and the first one is not a failure:

    run 1   no `report`   -> contact sheet + thumbnails, `described` 0
    run 2   `report`      -> the same sheet, plus the validated answers, `described` 1

Both artifacts persist because the report is part of the recipe. That is the
property that lets two readings of one scene sit side by side under sfm_compare
instead of one silently replacing the other.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from sfmkit import Ctx, module

# JPEG, not PNG. The sheet exists to be LOOKED AT, and `sfm_artifact_image`
# base64-encodes it onto the wire -- which inflates by 4/3. The same grid is
# ~1.7 MB as PNG and ~200 KB at quality 85, for no visible difference at 384px
# cells. Context cost is identical either way (image tokens follow dimensions,
# not bytes); this is purely transport. The individual thumbnails stay PNG,
# because those are for looking at one frame closely.
SHEET_NAME = "contact_sheet.jpg"
SHEET_QUALITY = 85
LABEL_H = 16
PAD = 4

# The rubric, in the only form a machine can check: which keys must be present,
# and which of them are closed vocabularies. The PROSE that explains how to answer
# them lives in skills/rubric.md and is expected to be revised; this is the part
# that must not drift from it silently, so the two are cross-checked by the test
# `test_the_rubric_doc_and_the_adapter_agree`.
# Closed vocabularies, checked wherever they appear. `subject_completeness` is
# among them and is NOT required -- it is contingent on `main_subject`, the same
# shape as `hazard_notes` against the two hazard enums.
ENUMS = {
    "environment": ("indoor", "outdoor", "studio", "mixed"),
    # There was a `capture_style` here -- turntable / orbit / walk_along / sweep /
    # aerial / unordered. Cut in v3: `rotation_median_deg`, `variability`,
    # `overall_magnitude` and `metadata.ordered` between them already say what the
    # camera did, and measured. One thing went with it: `sweep` was the way to
    # report a rotation-dominant pan that `pure_rotation_risk` misses because it
    # is computed over consecutive pairs only. Say that in `overall` instead.
    "repetition": ("none", "within_image", "between_images", "both"),
    "dynamic_content": ("none", "minor", "substantial"),
    "material_hazards": ("none", "minor", "substantial"),
    "subject_completeness": ("complete", "cropped", "occluded", "both"),
}
FREE_TEXT = ("main_subject", "subject", "empty_regions", "overall")
REQUIRED = (
    "environment", "main_subject", "subject", "empty_regions",
    "repetition", "dynamic_content", "material_hazards", "overall",
)
OPTIONAL = ("subject_completeness", "hazard_notes", "notes")

LEVEL = {"none": 0, "minor": 1, "substantial": 2}

# `main_subject` answers two things at once -- is there one, and what is it -- so
# the absence case needs a reserved word. Free text with a sentinel rather than a
# separate boolean, because "a cardboard box" and "no single subject" are answers
# to the same question and splitting them invites the two to disagree.
NO_SUBJECT = "none"


def has_main_subject(report: dict) -> bool:
    return str(report.get("main_subject", "")).strip().lower() not in ("", NO_SUBJECT)


def validate(report: dict) -> list[str]:
    """Shape only. Nothing here can tell whether the answers are TRUE.

    Worth being clear about what this buys, because it is easy to overrate: it
    stops a half-filled report from being recorded as a description, and it keeps
    the closed vocabularies closed so the derived metrics mean one thing. It does
    not make the report right.
    """
    problems = []

    for key in REQUIRED:
        if key not in report:
            problems.append(f"missing required field '{key}'")
        elif not str(report[key]).strip():
            problems.append(f"field '{key}' is empty")

    for key, allowed in ENUMS.items():
        if key in report and str(report[key]).strip() and report[key] not in allowed:
            problems.append(
                f"field '{key}' is '{report[key]}'; expected one of {list(allowed)}"
            )

    # A flagged hazard with no note is the failure mode this catches: the metric
    # goes up, the reader is told nothing about what or where, and the warning is
    # unactionable.
    flagged = [
        k for k in ("dynamic_content", "material_hazards")
        if report.get(k) in ("minor", "substantial")
    ]
    if flagged and not str(report.get("hazard_notes", "")).strip():
        problems.append(
            f"{flagged} flagged but 'hazard_notes' is empty. A hazard without a "
            f"note is a number nobody can act on."
        )

    # `subject_completeness` is only a question when there IS a main subject, and
    # is only answerable then. Both directions are checked: an unanswered one when
    # a subject was named, and an answered one when none was.
    completeness = str(report.get("subject_completeness", "")).strip()
    if has_main_subject(report) and not completeness:
        problems.append(
            f"'main_subject' is '{report['main_subject']}' but "
            f"'subject_completeness' is empty. Whether the thing being "
            f"reconstructed actually fits in the frames decides what coverage "
            f"downstream should be judged against."
        )
    if completeness and not has_main_subject(report):
        problems.append(
            f"'subject_completeness' is '{completeness}' while 'main_subject' is "
            f"'{report.get('main_subject')}'. There is nothing for it to describe."
        )

    unknown = sorted(set(report) - set(REQUIRED) - set(OPTIONAL))
    if unknown:
        # Not an error. The rubric is expected to grow, and an extra answer rides
        # into the artifact as an extra rather than being dropped on the floor.
        pass

    return problems


def load_thumbnails(scene, indices, max_side: int, ctx) -> list[Image.Image]:
    thumbs = []
    paths = scene.load("images", "paths")
    for n, i in enumerate(indices):
        ctx.progress(n / len(indices), f"thumbnail {n + 1}/{len(indices)}")
        with Image.open(scene.resolve(str(paths[i]))) as raw:
            img = raw.convert("RGB")
            img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
            thumbs.append(img.copy())
    return thumbs


def contact_sheet(thumbs, names, cols: int) -> Image.Image:
    """A single labelled grid.

    One image rather than N, because the question the sheet answers -- what is
    this capture, as a whole -- is about the set. The individual thumbnails are
    written too, for the questions that are about one frame.
    """
    cell_w = max(t.width for t in thumbs)
    cell_h = max(t.height for t in thumbs) + LABEL_H
    rows = (len(thumbs) + cols - 1) // cols

    sheet = Image.new(
        "RGB",
        (cols * (cell_w + PAD) + PAD, rows * (cell_h + PAD) + PAD),
        (24, 24, 24),
    )
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()

    for k, (thumb, name) in enumerate(zip(thumbs, names)):
        col, row = k % cols, k // cols
        x = PAD + col * (cell_w + PAD)
        y = PAD + row * (cell_h + PAD)
        sheet.paste(thumb, (x + (cell_w - thumb.width) // 2, y))
        # The index is what a report refers to when it says "the mirror in 7".
        label = f"[{k}] {name}"[:38]
        draw.text((x + 2, y + thumb.height + 2), label, fill=(210, 210, 210), font=font)

    return sheet


@module
def run(ctx: Ctx):
    scene = ctx.inputs["scene"]
    p = ctx.params

    names = [str(n) for n in scene.load("images", "names")]
    n_total = len(names)
    n = min(p.n_images, n_total)
    indices = (
        list(range(n)) if p.sampling == "head"
        else np.linspace(0, n_total - 1, n, dtype=int).tolist()
    )
    picked = [names[i] for i in indices]

    out = ctx.output("analysis")

    thumbs = load_thumbnails(scene, indices, p.thumbnail_max_side, ctx)
    browse = out.sidecar_dir("browse")
    sheet = contact_sheet(thumbs, picked, p.grid_cols)
    sheet.save(browse / SHEET_NAME, quality=SHEET_QUALITY)
    # The sheet is the ONLY image this module writes, and that is a decision.
    # Writing per-frame thumbnails too was the first design; they were redundant
    # -- the scene artifact already holds every working image at full resolution,
    # reachable as sfm_artifact_image(scene_id, 'images/000003.png'), which is
    # strictly better than a 384px copy for a question about one frame. Keeping
    # them also broke the tool's convenience path: with thirteen images in the
    # artifact, `sfm_artifact_image(id)` could never resolve without a name, and
    # the case it exists to make frictionless is exactly this one.

    report = dict(p.get("report") or {})
    described = bool(report)

    if described:
        problems = validate(report)
        if problems:
            raise ValueError(
                "the report does not satisfy the rubric:\n  - "
                + "\n  - ".join(problems)
                + "\n\nFetch it with sfm_module_skill('SceneDescription', 'rubric')."
            )

        payload = {
            # Declared in scene_analysis/v1. Everything else rides as an extra,
            # so revising the rubric does not mean revising the type.
            "overall": str(report["overall"]).strip(),
            "environment": report["environment"],
        }
        payload |= {
            k: str(v).strip()
            for k, v in report.items()
            if k not in payload and str(v).strip()
        }
        # Which images the viewer was actually shown. Without this the report is
        # a claim about a set nobody can reconstruct.
        payload["browsed"] = np.array(picked)
        out.save("description", **payload)

    out.metric("described", int(described), direction="neutral")
    out.metric("browse_images", len(indices), direction="neutral")
    out.metric(
        "dynamic_content",
        LEVEL[report["dynamic_content"]] if described else None,
        direction="lower_better", healthy=(None, 0),
    )
    out.metric(
        "material_hazards",
        LEVEL[report["material_hazards"]] if described else None,
        direction="lower_better", healthy=(None, 0),
    )
    out.metric(
        "between_image_repetition",
        int(report["repetition"] in ("between_images", "both")) if described else None,
        direction="lower_better", healthy=(None, 0),
    )
    subject = has_main_subject(report) if described else None
    out.metric(
        "has_main_subject",
        None if subject is None else int(subject),
        direction="neutral",
    )
    out.metric(
        "subject_complete",
        # Null on three different grounds -- no report, no subject, or a subject
        # whose completeness was not asked about. All three mean "not a claim".
        int(report.get("subject_completeness") == "complete") if subject else None,
        direction="higher_better", healthy=(1, None),
    )

    if not described:
        out.diagnostic(
            "awaiting_description",
            severity="info",
            message=(
                f"Contact sheet rendered from {len(indices)} of {n_total} images "
                f"({p.sampling}, {p.thumbnail_max_side}px cells). It is the only "
                f"image this artifact carries. No report supplied yet."
            ),
            suggested_actions=[
                "Look at it: sfm_artifact_image(this artifact). No `name` needed.",
                "Fetch the rubric with sfm_module_skill('SceneDescription', 'rubric').",
                "Re-run with params={'report': {...}}. Both artifacts persist.",
                "For one frame at full resolution, use the SCENE: "
                "sfm_artifact_image(scene_id, 'images/000003.png').",
            ],
            see_also="SKILL.md#the-two-call-flow",
        )
        out.note(
            f"Browse set rendered: {len(indices)} of {n_total} images at "
            f"{p.thumbnail_max_side}px, {p.grid_cols} columns. Awaiting a report."
        )
        return

    if LEVEL[report["dynamic_content"]] == 2:
        out.diagnostic(
            "dynamic_content",
            severity="warn",
            message=f"Substantial moving content: {report.get('hazard_notes', '')}",
            suggested_actions=[
                "Nothing downstream detects this; tracks through a mover are wrong and look right.",
                "Prefer a subset of frames without them; re-run SceneLoader over it.",
                "A healthy inlier_ratio is weak evidence here - moving points are locally consistent.",
            ],
            see_also="limitations.md#the-report-can-be-wrong",
        )

    if LEVEL[report["material_hazards"]] == 2:
        out.diagnostic(
            "material_hazards",
            severity="warn",
            message=f"Substantial reflective or transparent surface: "
                    f"{report.get('hazard_notes', '')}",
            suggested_actions=[
                "A reflection triangulates confidently to a point behind the surface.",
                "Expect structure that reprojects well and sits in the wrong place.",
            ],
            see_also="limitations.md#the-report-can-be-wrong",
        )

    if report["repetition"] in ("between_images", "both"):
        out.diagnostic(
            "between_image_repetition",
            severity="warn",
            message=(
                f"Structure reported recurring across different images "
                f"(repetition: {report['repetition']})."
            ),
            suggested_actions=[
                "SceneTriage's `repetitiveness` is blind to this; a low value there is not reassurance.",
                "Expect confident wrong matches; watch inlier_ratio rather than match count.",
                "Prefer a globally-reasoning matcher - sfm_find_alternatives("
                "produces='pairwise_matches/v1').",
            ],
            see_also="limitations.md#what-this-adds-over-the-measured-modules",
        )

    if subject and report.get("subject_completeness") != "complete":
        out.diagnostic(
            "incomplete_subject",
            severity="info",
            message=(
                f"The main subject ({report['main_subject']}) is "
                f"{report['subject_completeness']} rather than fully in view."
            ),
            suggested_actions=[
                "Judge downstream coverage against what is VISIBLE, not against the object.",
                "`cropped` is a framing limit of the capture; `occluded` means holes where "
                "something else is in the way. Neither is a pipeline fault.",
                "A low point count on the missing part is expected, not a failure to fix.",
            ],
            see_also="limitations.md#the-report-can-be-wrong",
        )

    # `overall` leads, and the structured answers follow it. This is the field a
    # reader acts on -- the enums are its machine-readable shadow, not a summary
    # of it -- so it goes where a reader's eye lands rather than after a header of
    # single words.
    out.note(
        f"{report['overall']}\n\n"
        f"---\n\n"
        f"Described from {len(indices)} of {n_total} images. {report['environment']}.\n"
        f"Main subject: {report['main_subject']}"
        + (f" -- {report['subject_completeness']}" if subject else "")
        + f"\nSubject: {report['subject']}\n"
        f"Empty regions: {report['empty_regions']}\n"
        f"Repetition: {report['repetition']}. "
        f"Dynamic content: {report['dynamic_content']}. "
        f"Material hazards: {report['material_hazards']}."
        + (f"\nHazard notes: {report['hazard_notes']}"
           if str(report.get("hazard_notes", "")).strip() else "")
    )
