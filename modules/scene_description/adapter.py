"""SceneDescription -- scene/v1 -> scene_analysis/v1. CPU, no model.

The odd one out. Every other module in this repository computes its output; this
one renders something to look at, and then stores what a viewer said about it.
The looking happens outside the container and there is no way for the module to
verify it -- which is exactly why the report is validated for SHAPE here and
marked as asserted rather than measured in the schema.

Two calls, and the first one is not a failure:

    run 1   no `report`   -> contact sheet, `described` 0
    run 2   `report`      -> the same sheet, plus the validated answers, `described` 1

Both artifacts persist because the report is part of the recipe. That is the
property that lets two readings of one scene sit side by side under sfm_compare
instead of one silently replacing the other.

Between those two calls sits a FIXED viewing protocol, and the fixity is the
point. The sheet is two downscales deep -- SceneLoader's, then the thumbnail's --
so on a 6200px ETH3D capture at `resize=fixed 1024` each cell is 6% of the
original linear scale and 0.4% of its pixels. Material, gloss, clipping and fine
texture are all decided below that. So the protocol is: the sheet, then exactly
two frames at full resolution, and always the same two -- the FIRST and LAST of
the browse set. Named here rather than chosen, because a viewer who picks their
own two picks the interesting ones, and then no two scenes were read the same
way. The module writes their names into the artifact so the reading is
repeatable; it cannot verify that anyone looked.
"""

from __future__ import annotations

import re

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
DATA_PREFIX = "data/"

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
    # There was a `repetition` enum here from v1 to v6 and it is gone in v7.
    # It was graded four ways in four revisions -- four values, then two enums,
    # then one enum, then a yes/no -- and it never discriminated: `both` on
    # eleven of fourteen readings, then `present` on eight of eight. The last
    # version had already reduced it to a gate meaning "read the note", and a
    # gate that is always open is not a gate. The note is the field, and it is
    # required unconditionally. See `repetition_notes` below.
    "dynamic_content": ("none", "minor", "substantial"),
    # v6 regrades this by COHERENCE rather than by position, because coherence is
    # the mechanism. The documented failure -- a correspondence to a virtual point
    # behind the surface that triangulates confidently and reprojects beautifully
    # -- requires the reflection to carry a legible IMAGE. A diffuse highlight
    # makes no virtual point; it makes a brightness gradient that moves, which
    # causes drift and dropout instead. Different failures, different responses,
    # and the old WHERE rule graded them the same.
    "material_hazards": ("none", "diffuse", "coherent"),
    # Where it is decides where the phantom LANDS, which is the other half and is
    # genuinely independent. Split out because the old single axis could not
    # express a mirror standing BETWEEN the camera and the subject -- the worst
    # case, and the one the WHERE rule graded mildest -- and because "on the
    # subject" is undefined on the four scenes here that report no main subject.
    "hazard_position": ("background", "on_subject",
                        "between_camera_and_subject", "throughout"),
    "subject_completeness": ("complete", "cropped", "occluded", "both"),
}
FREE_TEXT = ("main_subject", "subject", "empty_regions", "third_frame", "overall")
REQUIRED = (
    "environment", "main_subject", "subject", "empty_regions",
    "dynamic_content", "material_hazards", "third_frame", "overall",
)
# `repetition_notes` is required too, but it is a mapping rather than a string,
# so the REQUIRED sweep cannot check it and it has its own block in `validate`.
OPTIONAL = ("subject_completeness", "hazard_notes", "hazard_position", "notes")

LEVEL = {"none": 0, "minor": 1, "substantial": 2}
# Coherence, ordered by what it can do to a reconstruction: nothing, drift,
# phantom geometry.
REFLECT = {"none": 0, "diffuse": 1, "coherent": 2}
# Codes, not a severity ordering -- see the metric's `meaning`. `background` is
# usually the mildest and `between_camera_and_subject` the worst, but `throughout`
# is not "worse than" the others, it is a different shape of problem.
POSITION = {"background": 0, "on_subject": 1,
            "between_camera_and_subject": 2, "throughout": 3}
# The two halves the note must answer separately. Enforced as a mapping rather
# than sniffed for keywords in prose: a check that can be satisfied by writing
# the word "texture" somewhere is not a check.
REPEAT_PARTS = ("texture", "objects")
# One or two sentences each, and the cap is enforced. The note is now carrying
# the whole field, so the temptation is to let it grow into a second `overall`
# -- which would put the reasoning in two places and leave a reader unsure which
# to act on. Roughly two sentences of ordinary prose.
NOTE_MAX_CHARS = 260

# `third_frame` names a browse cell as `[k]` and then says why that one. The
# reason is checked for existence, not for quality -- the threshold is set low
# enough that a terse real reason passes, because the failure being caught is a
# bare `[5]` with nothing after it. Separators are stripped first so that
# "[5] - the last one" is measured on the words rather than on the dash.
CELL_RE = re.compile(r"\[(\d+)\]")
SEPARATORS = " -–—:,."
REASON_MIN_CHARS = 8

# `main_subject` answers two things at once -- is there one, and what is it -- so
# the absence case needs a reserved word. Free text with a sentinel rather than a
# separate boolean, because "a cardboard box" and "no single subject" are answers
# to the same question and splitting them invites the two to disagree.
NO_SUBJECT = "none"


def has_main_subject(report: dict) -> bool:
    return str(report.get("main_subject", "")).strip().lower() not in ("", NO_SUBJECT)


def third_frame_index(report: dict, n_cells: int) -> tuple[int | None, list[str]]:
    """Parse and vet the free-choice frame. Returns (index, problems).

    This is the one part of the report a machine CAN check, and it is worth
    checking properly: the first and last frames are prescribed, so the third is
    the only place a reader exercises judgement, and a choice that does not
    resolve to a real cell is a claim about an image nobody opened.
    """
    raw = str(report.get("third_frame", "")).strip()
    if not raw:
        return None, []  # the REQUIRED sweep already reported it

    match = CELL_RE.search(raw)
    if not match:
        return None, [
            f"'third_frame' is {raw!r} and does not name a cell. Give the index "
            f"in brackets and then the reason, e.g. '[5] - the only frame where "
            f"the whole reflector is in view'."
        ]

    k = int(match.group(1))
    problems = []
    if not 0 <= k < n_cells:
        problems.append(
            f"'third_frame' names cell [{k}] but the browse set has {n_cells} "
            f"cells, [0] to [{n_cells - 1}]."
        )
    elif k in (0, n_cells - 1):
        problems.append(
            f"'third_frame' names cell [{k}], which is already prescribed -- "
            f"[0] and [{n_cells - 1}] are opened on every scene. The third view "
            f"exists to add coverage those two do not have. Pick another."
        )
    reason = raw.replace(match.group(0), "", 1).strip(SEPARATORS).strip()
    if len(reason) < REASON_MIN_CHARS:
        problems.append(
            f"'third_frame' is {raw!r} with no reason attached. Why that cell? "
            f"The choice is the only judgement in the viewing protocol and an "
            f"unexplained one cannot be reviewed."
        )
    return (k if not problems else None), problems


def validate(report: dict, n_cells: int) -> list[str]:
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
        if report.get(k) not in (None, "", "none")
    ]
    if flagged and not str(report.get("hazard_notes", "")).strip():
        problems.append(
            f"{flagged} flagged but 'hazard_notes' is empty. A hazard without a "
            f"note is a number nobody can act on."
        )

    # `hazard_position` is to `material_hazards` what `subject_completeness` is to
    # `main_subject`: only a question when there is something to ask it about, and
    # then a required one. Checked both ways, because a position asserted with no
    # reflector to place is as wrong as a reflector nobody located.
    reflective = report.get("material_hazards") not in (None, "", "none")
    position = str(report.get("hazard_position", "")).strip()
    if reflective and not position:
        problems.append(
            f"'material_hazards' is '{report['material_hazards']}' but "
            f"'hazard_position' is empty. Coherence says WHETHER phantom geometry "
            f"is possible; position says WHERE it lands, and they are independent "
            f"-- a mirror in the background is a curiosity, the same mirror "
            f"between the camera and the subject is a hole in the model."
        )
    if position and not reflective:
        problems.append(
            f"'hazard_position' is '{position}' while 'material_hazards' is "
            f"'{report.get('material_hazards')}'. There is nothing to place."
        )

    # Same shape as `hazard_notes`, with one extra demand: the note must answer
    # BOTH halves separately. Repeating surface pattern and repeating objects
    # want opposite responses -- context and scale separate a pattern and cannot
    # separate two castings of one mould -- and the single level cannot say which
    # is in play. A mapping rather than prose, because a keyword check on prose
    # is satisfied by writing the word.
    # Unconditional since v7. Every capture worth describing has SOMETHING that
    # recurs, and the four graded versions of the old enum proved it -- the last
    # of them read `present` on eight scenes out of eight. So the question is not
    # whether there is repetition but what kind, and that is asked of every
    # report. `none` is a legitimate answer to either half and is a finding when
    # it is true: DTU scan33's stone is genuinely aperiodic, and saying so is
    # what makes its two identical ear cups the whole story.
    #
    # A mapping rather than prose, because a keyword check on prose is satisfied
    # by writing the word.
    note = report.get("repetition_notes")
    if not isinstance(note, dict):
        problems.append(
            f"'repetition_notes' is {type(note).__name__} and must be a mapping "
            f"with both of {list(REPEAT_PARTS)}. Repeating surface PATTERN and "
            f"repeating OBJECTS have opposite escapes -- context and scale "
            f"separate a pattern and cannot separate two castings of one mould "
            f"-- so they are answered separately or not usefully at all."
        )
    else:
        for part in REPEAT_PARTS:
            answer = str(note.get(part, "")).strip()
            if not answer:
                problems.append(
                    f"'repetition_notes[{part}]' is empty. Answer it even when "
                    f"the answer is 'none' -- a blank half reads as an oversight, "
                    f"and 'none' is a finding."
                )
            elif len(answer) > NOTE_MAX_CHARS:
                problems.append(
                    f"'repetition_notes[{part}]' is {len(answer)} characters; "
                    f"the cap is {NOTE_MAX_CHARS}, about two sentences. Say what "
                    f"repeats and in which cells; argue it in `overall`."
                )

    problems.extend(third_frame_index(report, n_cells)[1])

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

    # Full-resolution frames, as `sfm_artifact_image` wants them -- relative to
    # the SCENE artifact's data directory, because that is where the images live
    # at full resolution. `paths` are recorded relative to the artifact root
    # (`data/images/000000.png`) and the tool resolves names under `data/`, so
    # the prefix comes off.
    stored = [str(x) for x in scene.load("images", "paths")]

    def frame_name(cell: int) -> str:
        p = stored[indices[cell]]
        return p[len(DATA_PREFIX):] if p.startswith(DATA_PREFIX) else p

    # Two are prescribed on every scene; the third is the reader's, and it is
    # validated against the browse set rather than taken on trust.
    prescribed = [frame_name(0), frame_name(len(indices) - 1)]

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
        problems = validate(report, len(indices))
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
        # The two-part note is a mapping and npz holds flat arrays, so it lands
        # as two keys. Flattened here rather than in the rubric, because the
        # rubric's job is to make the reader answer both halves and storage
        # should not shape that.
        note = report.get("repetition_notes")
        if isinstance(note, dict):
            report = report | {
                f"repetition_{part}": note.get(part, "") for part in REPEAT_PARTS
            }
            report.pop("repetition_notes")

        payload |= {
            k: str(v).strip()
            for k, v in report.items()
            if k not in payload and str(v).strip()
        }
        # Which images the viewer was actually shown. Without this the report is
        # a claim about a set nobody can reconstruct.
        payload["browsed"] = np.array(picked)
        # And the three opened at full resolution: two prescribed, one chosen.
        # This records what the protocol REQUIRED, not what was looked at --
        # nothing here can know that. Its value is that a second reader can
        # repeat the reading exactly, including the choice and its reason.
        chosen = third_frame_index(report, len(indices))[0]
        payload["full_res_frames"] = np.array(prescribed + [frame_name(chosen)])
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
        REFLECT[report["material_hazards"]] if described else None,
        # 0 none, 1 diffuse, 2 coherent. Band ends at 0: a diffuse reflector is
        # not harmless, it is a different harm, and it gets its own diagnostic
        # rather than being folded in with the one that predicts phantom points.
        direction="lower_better", healthy=(None, 0),
    )
    out.metric(
        "hazard_position",
        # Null on two grounds that mean the same thing: no report, or no
        # reflector to place. Neither is a claim that it is in the background.
        POSITION.get(report.get("hazard_position")) if described else None,
        direction="neutral",
    )
    out.metric(
        # Not a quality number. It records WHICH cell the reader chose to open,
        # so a run of readings can be audited for where judgement keeps landing
        # -- and, less comfortably, for whether it lands anywhere interesting.
        "third_frame",
        third_frame_index(report, len(indices))[0] if described else None,
        direction="neutral",
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
                "1. Look at the sheet: sfm_artifact_image(this artifact). "
                "No `name` needed - it is the only image here.",
                f"2. Then THREE frames at full resolution, from the SCENE. Two "
                f"are fixed on every scene - the first and last of the sheet: "
                f"sfm_artifact_image('{scene.id}', '{prescribed[0]}') then "
                f"sfm_artifact_image('{scene.id}', '{prescribed[1]}'). "
                f"The sheet's cells are {p.thumbnail_max_side}px of an already "
                f"downscaled frame; gloss, clipping and fine texture are not "
                f"decidable there.",
                f"3. Then ONE cell of your choosing from [1] to "
                f"[{len(indices) - 2}], for whatever the fixed two do not "
                f"settle. Name it and say why in the report's `third_frame` "
                f"field - '[5] - the only cell with the whole reflector in "
                f"view'. It is checked against the browse set.",
                "4. Fetch the rubric: "
                "sfm_module_skill('SceneDescription', 'rubric').",
                "5. Re-run with params={'report': {...}}. Both artifacts persist.",
            ],
            see_also="SKILL.md#the-two-call-flow",
        )
        out.note(
            f"Browse set rendered: {len(indices)} of {n_total} images at "
            f"{p.thumbnail_max_side}px, {p.grid_cols} columns.\n"
            f"Full-resolution frames for this reading: {prescribed[0]} and "
            f"{prescribed[1]} are fixed (from scene {scene.id}); one more from "
            f"[1] to [{len(indices) - 2}] is the reader's, named in "
            f"`third_frame`.\n"
            f"Awaiting a report."
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
            see_also="tuning.md#coherent-reflection",
        )

    # Two codes rather than one severity that changes, because a diagnostic's
    # severity is declared in the manifest and a code whose severity moves cannot
    # be checked against it. They also carry genuinely different advice, which is
    # the whole reason coherence was split out from position.
    position = report.get("hazard_position", "")
    lands = {
        "between_camera_and_subject":
            "It stands BETWEEN the camera and the subject, which is the worst "
            "case: the virtual points land close in, inside the model you wanted.",
        "on_subject":
            "It is ON the subject, so the phantom structure lands on the surface "
            "being reconstructed.",
        "background":
            "It is in the BACKGROUND, so expect spurious points somewhere nobody "
            "is looking. Often ignorable - decide before spending time on it.",
        "throughout":
            "It is across most of the frame, so no part of the model is clear of it.",
    }.get(position, "")
    # A glossy patch with no image in it plants no virtual point, so its position
    # says where the model thins or drifts -- never where phantom structure lands.
    # Sharing `lands` with the diffuse case told readers the opposite of this
    # diagnostic's own first action.
    thins = {
        "between_camera_and_subject":
            "It stands BETWEEN the camera and the subject, so the correspondences "
            "seen through it drift or drop, and the model behind it thins.",
        "on_subject":
            "It is ON the subject, so expect that part of the surface to thin or "
            "drift in the model - not to gain phantom points.",
        "background":
            "It is in the BACKGROUND, so expect thinning somewhere nobody is "
            "looking. Usually ignorable.",
        "throughout":
            "It is across most of the frame, so expect thinning or drift wherever "
            "it falls.",
    }.get(position, "")

    if REFLECT[report["material_hazards"]] == 2:
        out.diagnostic(
            "coherent_reflection",
            severity="warn",
            message=(
                f"A reflective surface carrying a legible image was reported "
                f"({position}). {report.get('hazard_notes', '')}"
            ),
            suggested_actions=[
                "A coherent reflection is a correspondence to a virtual point BEHIND "
                "the surface. Bundle adjustment will not remove it: measured, the "
                "flagged region's error ratio was unchanged either side of a global "
                "solve.",
                "BUT REPROJECTION ERROR IS NOT BLIND TO IT, and an earlier version "
                "of this action said it was. Point by point a virtual point does "
                "reproject well. As a POPULATION it does not -- measured at 3.1x the "
                "mean error of the rest of the model. Several readers stopped "
                "looking because this action told them not to.",
                "So the cheap probe is worth taking: read p95_reprojection_error "
                "beside mean_reprojection_error on the finished model, and compare "
                "error DISTRIBUTIONS over the flagged region, never individual "
                "points.",
                lands,
                "Those features are self-consistent, so they can be RANSAC inliers. "
                "A healthy inlier_ratio is not evidence against this, and neither "
                "is a healthy MEAN.",
            ],
            see_also="limitations.md#the-report-can-be-wrong",
        )

    if REFLECT[report["material_hazards"]] == 1:
        out.diagnostic(
            "diffuse_reflection",
            severity="info",
            message=(
                f"A glossy surface with no legible reflected image was reported "
                f"({position}). {report.get('hazard_notes', '')}"
            ),
            suggested_actions=[
                "This is NOT the phantom-geometry case - a highlight with no image in "
                "it creates no virtual point. Do not go looking for structure in the "
                "wrong place.",
                "Expect the opposite failure: a bright patch that moves with the "
                "camera rather than the surface, so correspondences there drift or "
                "drop out and that part of the model thins.",
                thins,
            ],
            see_also="limitations.md#the-report-can-be-wrong",
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
        f"Dynamic content: {report['dynamic_content']}. "
        f"Material hazards: {report['material_hazards']}"
        + (f" ({report['hazard_position']})"
           if str(report.get("hazard_position", "")).strip() else "")
        + "."
        + f"\nRepetition, texture: {report['repetition_texture']}"
        + f"\nRepetition, objects: {report['repetition_objects']}"
        + (f"\nHazard notes: {report['hazard_notes']}"
           if str(report.get("hazard_notes", "")).strip() else "")
        + f"\nRead from the sheet plus three frames at full resolution: "
          f"{prescribed[0]}, {prescribed[1]}, and {report['third_frame']}"
    )
