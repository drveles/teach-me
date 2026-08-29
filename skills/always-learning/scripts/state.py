#!/usr/bin/env python3

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


SCHEMA_VERSION = 1
INTERVAL_DAYS = (1, 3, 7, 14, 30, 60)
RATINGS = ("again", "hard", "good", "easy")
IDENTIFIER = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ENTRY_HEADING = re.compile(r"(?m)^### `([^`]+)`[ \t]*$")
FIELD = re.compile(r"(?m)^- ([A-Za-z ]+):[ \t]*(.*\S)[ \t]*$")
SUBJECT_FILES = ("MISSION.md", "RESOURCES.md", "PLAN.md", "mastery.json", "events.jsonl")


class StateError(Exception):
    pass


def resolve_home(value):
    if value:
        return Path(value).expanduser()
    configured = os.environ.get("ALWAYS_LEARNING_HOME")
    if configured:
        return Path(configured).expanduser()
    data_home = os.environ.get("XDG_DATA_HOME")
    if data_home:
        return Path(data_home).expanduser() / "always-learning"
    return Path.home() / ".local" / "share" / "always-learning"


def require_identifier(value, label):
    if not IDENTIFIER.fullmatch(value):
        raise StateError(f"{label} must be a lowercase hyphenated identifier: {value}")


def parse_time(value):
    if value is None:
        return datetime.now(timezone.utc)
    if not isinstance(value, str):
        raise StateError(f"timestamp must be text: {value}")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise StateError(f"invalid ISO-8601 timestamp: {value}") from error
    if parsed.tzinfo is None:
        raise StateError(f"timestamp must include a timezone: {value}")
    return parsed.astimezone(timezone.utc)


def format_time(value):
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise StateError(f"missing state file: {path}") from error
    except json.JSONDecodeError as error:
        raise StateError(f"invalid JSON in {path}: {error}") from error


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def emit(value):
    print(json.dumps(value, indent=2, ensure_ascii=False))


def registry_path(home):
    return home / "registry.json"


def subject_path(home, subject_id):
    return home / "subjects" / subject_id


def load_registry(home):
    value = read_json(registry_path(home))
    errors = registry_errors(value)
    if errors:
        raise StateError("\n".join(errors))
    return value


def find_subject(registry, subject_id):
    for subject in registry.get("subjects", []):
        if subject.get("id") == subject_id:
            return subject
    raise StateError(f"unknown subject: {subject_id}")


def read_events(path):
    events = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise StateError(f"invalid event JSON at {path}:{number}") from error
    return events


def section_body(text, title, path):
    match = re.search(
        rf"(?ms)^## {re.escape(title)}[ \t]*\n(.*?)(?=^## [^#]|\Z)",
        text,
    )
    if not match:
        raise StateError(f"missing ## {title} section in {path}")
    return match.group(1)


def entry_blocks(body, path, kind):
    matches = list(ENTRY_HEADING.finditer(body))
    entries = []
    seen = set()
    for index, match in enumerate(matches):
        identifier = match.group(1)
        require_identifier(identifier, f"{kind} id")
        if identifier in seen:
            raise StateError(f"duplicate {kind} id in {path}: {identifier}")
        seen.add(identifier)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        fields = {}
        for field in FIELD.finditer(body[match.end():end]):
            name = field.group(1).strip().lower().replace(" ", "_")
            if name in fields:
                raise StateError(f"duplicate {name} for {kind} {identifier} in {path}")
            fields[name] = field.group(2).strip()
        entries.append((identifier, fields))
    return entries


def read_sources(path):
    text = path.read_text(encoding="utf-8")
    entries = entry_blocks(section_body(text, "Sources", path), path, "source")
    sources = {}
    for identifier, fields in entries:
        missing = [name for name in ("link", "purpose", "verified") if not fields.get(name)]
        if missing:
            raise StateError(
                f"source {identifier} in {path} is missing: {', '.join(missing)}"
            )
        try:
            datetime.strptime(fields["verified"], "%Y-%m-%d")
        except ValueError as error:
            raise StateError(
                f"source {identifier} in {path} has invalid verified date: {fields['verified']}"
            ) from error
        sources[identifier] = {
            "id": identifier,
            "link": fields["link"],
            "purpose": fields["purpose"],
            "verified": fields["verified"],
        }
    return sources


def read_objectives(path):
    text = path.read_text(encoding="utf-8")
    entries = entry_blocks(section_body(text, "Objectives", path), path, "objective")
    objectives = {}
    for identifier, fields in entries:
        missing = [name for name in ("outcome", "concepts", "depends_on") if not fields.get(name)]
        if missing:
            raise StateError(
                f"objective {identifier} in {path} is missing: {', '.join(missing)}"
            )
        concepts = [value.strip() for value in fields["concepts"].split(",") if value.strip()]
        if not concepts:
            raise StateError(f"objective {identifier} in {path} needs concepts")
        dependency_text = fields["depends_on"]
        dependencies = [] if dependency_text.lower() == "none" else [
            value.strip() for value in dependency_text.split(",") if value.strip()
        ]
        for dependency in dependencies:
            require_identifier(dependency, f"dependency for objective {identifier}")
        objectives[identifier] = {
            "id": identifier,
            "outcome": fields["outcome"],
            "concepts": concepts,
            "depends_on": dependencies,
        }
    known = set(objectives)
    for objective in objectives.values():
        unknown = sorted(set(objective["depends_on"]) - known)
        if unknown:
            names = ", ".join(unknown)
            raise StateError(
                f"objective {objective['id']} in {path} has unknown dependencies: {names}"
            )
    visiting = set()
    visited = set()

    def visit(identifier, trail):
        if identifier in visiting:
            cycle = " -> ".join([*trail, identifier])
            raise StateError(f"objective dependency cycle in {path}: {cycle}")
        if identifier in visited:
            return
        visiting.add(identifier)
        for dependency in objectives[identifier]["depends_on"]:
            visit(dependency, [*trail, identifier])
        visiting.remove(identifier)
        visited.add(identifier)

    for identifier in objectives:
        visit(identifier, [])
    return objectives


def mission_errors(path):
    text = path.read_text(encoding="utf-8")
    errors = []
    for title in ("Outcome", "Success Criteria", "Constraints", "Out of Scope"):
        try:
            body = section_body(text, title, path)
            if not body.strip():
                errors.append(f"empty ## {title} section in {path}")
        except StateError as error:
            errors.append(str(error))
    return errors


def dependency_blockers(objective_id, objectives, items):
    objective = objectives.get(objective_id)
    if objective is None:
        return []
    return [
        dependency
        for dependency in objective["depends_on"]
        if dependency not in items
        or items[dependency].get("last_rating") not in ("good", "easy")
    ]


def command_status(args):
    home = resolve_home(args.home)
    if not registry_path(home).is_file():
        emit({"configured": False, "enabled": False, "subjects": [], "due": []})
        return
    registry = load_registry(home)
    now = parse_time(args.now)
    subjects = registry.get("subjects", [])
    due = []
    summaries = []
    issues = []
    for subject in subjects:
        summary = dict(subject)
        summaries.append(summary)
        if not (
            registry.get("enabled")
            and subject.get("enabled")
            and subject.get("ready")
        ):
            continue
        try:
            state, errors = validate_subject_state(home, subject["id"])
            if errors:
                raise StateError("\n".join(errors))
        except (OSError, StateError) as error:
            issues.append({"subject_id": subject["id"], "error": str(error)})
            continue
        mastery = state["mastery"]
        events = state["events"]
        items = {item["id"]: item for item in mastery["items"]}
        latest = {}
        for event in events:
            latest[event["item_id"]] = event
        summary["objectives"] = list(state["objectives"].values())
        summary["item_count"] = len(mastery.get("items", []))
        summary["review_count"] = len(events)
        summary["last_reviewed_at"] = events[-1].get("reviewed_at") if events else None
        summary["items"] = [
            {
                "id": item["id"],
                "objective": item["objective"],
                "concepts": item["concepts"],
                "stage": item["stage"],
                "due_at": item["due_at"],
                "last_reviewed_at": item["last_reviewed_at"],
                "last_rating": item["last_rating"],
                "blocked_by": dependency_blockers(
                    item["id"], state["objectives"], items
                ),
                "last_evidence": latest.get(item["id"], {}).get("evidence"),
                "last_confidence": latest.get(item["id"], {}).get("confidence"),
            }
            for item in mastery["items"]
        ]
        for item in mastery.get("items", []):
            if (
                not dependency_blockers(item["id"], state["objectives"], items)
                and parse_time(item["due_at"]) <= now
            ):
                due.append(
                    {
                        "subject_id": subject["id"],
                        "subject_title": subject["title"],
                        "item_id": item["id"],
                        "objective": item["objective"],
                        "prompt": item["prompt"],
                        "concepts": item.get("concepts", []),
                        "due_at": item["due_at"],
                        "stage": item["stage"],
                        "last_rating": item.get("last_rating"),
                    }
                )
    due.sort(key=lambda item: (item["due_at"], item["subject_id"], item["item_id"]))
    emit(
        {
            "configured": True,
            "enabled": bool(registry.get("enabled")),
            "subjects": summaries,
            "due": due,
            "issues": issues,
        }
    )


def command_init_subject(args):
    home = resolve_home(args.home)
    require_identifier(args.id, "subject id")
    title = args.title.strip()
    mission = args.mission.strip()
    if not title or not mission:
        raise StateError("title and mission must not be empty")
    path = subject_path(home, args.id)
    if path.exists():
        raise StateError(f"subject already exists: {args.id}")
    registry_file = registry_path(home)
    if registry_file.is_file():
        registry = load_registry(home)
        if any(subject.get("id") == args.id for subject in registry.get("subjects", [])):
            raise StateError(f"subject already exists: {args.id}")
    else:
        registry = {"schema_version": SCHEMA_VERSION, "enabled": True, "subjects": []}
    subject = {
        "id": args.id,
        "title": title,
        "mission": mission,
        "enabled": True,
        "ready": False,
        "cues": list(dict.fromkeys(cue.strip() for cue in args.cue if cue.strip())),
    }
    subjects_root = home / "subjects"
    subjects_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{args.id}.", dir=subjects_root))
    moved = False
    registered = False
    try:
        (temporary / "MISSION.md").write_text(
            f"# {subject['title']}\n\n## Outcome\n\n{subject['mission']}\n",
            encoding="utf-8",
        )
        (temporary / "RESOURCES.md").write_text(
            "# Resources\n\n## Sources\n\n## Gaps\n",
            encoding="utf-8",
        )
        (temporary / "PLAN.md").write_text(
            "# Plan\n\n## Objectives\n\n## Dependencies\n",
            encoding="utf-8",
        )
        write_json(temporary / "mastery.json", {"schema_version": SCHEMA_VERSION, "items": []})
        (temporary / "events.jsonl").touch(exist_ok=False)
        os.replace(temporary, path)
        moved = True
        registry.setdefault("subjects", []).append(subject)
        write_json(registry_file, registry)
        registered = True
    except Exception:
        if moved and not registered and path.exists():
            shutil.rmtree(path)
        raise
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    emit(subject)


def command_add_item(args):
    home = resolve_home(args.home)
    require_identifier(args.subject, "subject id")
    require_identifier(args.id, "item id")
    registry = load_registry(home)
    find_subject(registry, args.subject)
    subject_root = subject_path(home, args.subject)
    path = subject_root / "mastery.json"
    mastery = read_json(path)
    known_sources = set(read_sources(subject_root / "RESOURCES.md"))
    known_objectives = read_objectives(subject_root / "PLAN.md")
    errors = mastery_errors(mastery, path, known_sources)
    if errors:
        raise StateError("\n".join(errors))
    if any(item.get("id") == args.id for item in mastery.get("items", [])):
        raise StateError(f"item already exists: {args.id}")
    criteria = [value.strip() for value in args.criterion if value.strip()]
    if not criteria:
        raise StateError("at least one answer criterion is required")
    concepts = list(dict.fromkeys(value.strip() for value in args.concept if value.strip()))
    sources = list(dict.fromkeys(value.strip() for value in args.source if value.strip()))
    if not concepts or not sources:
        raise StateError("at least one concept and source are required")
    if args.id not in known_objectives:
        raise StateError(f"item id is not a planned objective: {args.id}")
    unknown_sources = sorted(set(sources) - known_sources)
    if unknown_sources:
        raise StateError(f"unknown source ids: {', '.join(unknown_sources)}")
    item = {
        "id": args.id,
        "objective": args.objective.strip(),
        "prompt": args.prompt.strip(),
        "answer_criteria": criteria,
        "concepts": concepts,
        "source_ids": sources,
        "stage": -1,
        "due_at": format_time(parse_time(args.due_at)),
        "last_reviewed_at": None,
        "last_rating": None,
    }
    if not item["objective"] or not item["prompt"]:
        raise StateError("objective and prompt must not be empty")
    mastery.setdefault("items", []).append(item)
    write_json(path, mastery)
    emit(item)


def next_schedule(stage, rating, now):
    if rating == "again":
        next_stage = 0
        days = 1
    elif rating == "hard":
        next_stage = max(stage - 1, 0)
        days = INTERVAL_DAYS[next_stage]
    elif rating == "good":
        next_stage = min(max(stage + 1, 0), len(INTERVAL_DAYS) - 1)
        days = INTERVAL_DAYS[next_stage]
    else:
        next_stage = min(max(stage + 2, 1), len(INTERVAL_DAYS) - 1)
        days = INTERVAL_DAYS[next_stage]
    return next_stage, now + timedelta(days=days)


def command_record_review(args):
    home = resolve_home(args.home)
    if not 1 <= args.confidence <= 5:
        raise StateError("confidence must be between 1 and 5")
    evidence = args.evidence.strip()
    if not evidence:
        raise StateError("evidence must not be empty")
    registry = load_registry(home)
    subject = find_subject(registry, args.subject)
    if not registry["enabled"]:
        raise StateError("learning is paused")
    if not subject["enabled"]:
        raise StateError(f"subject is paused: {args.subject}")
    if not subject["ready"]:
        raise StateError(f"subject is not ready: {args.subject}")
    path = subject_path(home, args.subject)
    state, errors = validate_subject_state(home, args.subject)
    if errors:
        raise StateError("\n".join(errors))
    mastery_path = path / "mastery.json"
    mastery = state["mastery"]
    events_path = path / "events.jsonl"
    events = state["events"]
    item = next(
        (value for value in mastery.get("items", []) if value.get("id") == args.item),
        None,
    )
    if item is None:
        raise StateError(f"unknown item: {args.item}")
    items = {value["id"]: value for value in mastery["items"]}
    blockers = dependency_blockers(args.item, state["objectives"], items)
    if blockers:
        raise StateError(f"item dependencies are not ready: {', '.join(blockers)}")
    now = parse_time(args.now)
    if events and now < parse_time(events[-1]["reviewed_at"]):
        raise StateError("review timestamp is earlier than existing evidence")
    stage, due_at = next_schedule(item.get("stage", -1), args.rating, now)
    item["stage"] = stage
    item["due_at"] = format_time(due_at)
    item["last_reviewed_at"] = format_time(now)
    item["last_rating"] = args.rating
    event = {
        "reviewed_at": format_time(now),
        "item_id": args.item,
        "rating": args.rating,
        "confidence": args.confidence,
        "evidence": evidence,
        "next_stage": stage,
        "next_due_at": item["due_at"],
    }
    encoded_event = (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8")
    with events_path.open("r+b") as stream:
        stream.seek(0, os.SEEK_END)
        previous_size = stream.tell()
        try:
            stream.write(encoded_event)
            stream.flush()
            os.fsync(stream.fileno())
            write_json(mastery_path, mastery)
        except Exception:
            stream.seek(previous_size)
            stream.truncate()
            stream.flush()
            os.fsync(stream.fileno())
            raise
    emit({"item_id": args.item, "stage": stage, "due_at": item["due_at"]})


def command_set_enabled(args):
    home = resolve_home(args.home)
    registry = load_registry(home)
    enabled = bool(args.enabled)
    if args.subject:
        subject = find_subject(registry, args.subject)
        subject["enabled"] = enabled
    else:
        registry["enabled"] = enabled
    write_json(registry_path(home), registry)
    emit({"subject": args.subject, "enabled": enabled})


def registry_errors(registry):
    errors = []
    if not isinstance(registry, dict):
        return ["registry must be an object"]
    if registry.get("schema_version") != SCHEMA_VERSION:
        errors.append("unsupported registry schema version")
    if type(registry.get("enabled")) is not bool:
        errors.append("registry enabled must be a boolean")
    subjects = registry.get("subjects")
    if not isinstance(subjects, list):
        errors.append("registry subjects must be a list")
        return errors
    seen = set()
    for index, subject in enumerate(subjects):
        label = f"registry subject {index}"
        if not isinstance(subject, dict):
            errors.append(f"{label} must be an object")
            continue
        subject_id = subject.get("id")
        if not isinstance(subject_id, str) or not IDENTIFIER.fullmatch(subject_id):
            errors.append(f"{label} has invalid id: {subject_id}")
        elif subject_id in seen:
            errors.append(f"duplicate subject id: {subject_id}")
        else:
            seen.add(subject_id)
        for field in ("title", "mission"):
            if not isinstance(subject.get(field), str) or not subject[field].strip():
                errors.append(f"{label} {field} must be non-empty text")
        if type(subject.get("enabled")) is not bool:
            errors.append(f"{label} enabled must be a boolean")
        if type(subject.get("ready")) is not bool:
            errors.append(f"{label} ready must be a boolean")
        cues = subject.get("cues")
        if not isinstance(cues, list) or any(
            not isinstance(value, str) or not value.strip() for value in cues
        ):
            errors.append(f"{label} cues must be a list of non-empty strings")
    return errors


def mastery_errors(mastery, path, source_ids):
    errors = []
    if not isinstance(mastery, dict):
        return [f"mastery must be an object: {path}"]
    if mastery.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"unsupported mastery schema version: {path}")
    items = mastery.get("items")
    if not isinstance(items, list):
        errors.append(f"items must be a list: {path}")
        return errors
    seen = set()
    for index, item in enumerate(items):
        label = f"item {index} in {path}"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        item_id = item.get("id")
        if not isinstance(item_id, str) or not IDENTIFIER.fullmatch(item_id):
            errors.append(f"{label} has invalid id: {item_id}")
        elif item_id in seen:
            errors.append(f"duplicate item id in {path}: {item_id}")
        else:
            seen.add(item_id)
        for field in ("objective", "prompt"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                errors.append(f"{label} {field} must be non-empty text")
        for field in ("answer_criteria", "concepts", "source_ids"):
            values = item.get(field)
            if not isinstance(values, list) or not values or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                errors.append(f"{label} {field} must be a non-empty string list")
        values = item.get("source_ids")
        if isinstance(values, list) and all(isinstance(value, str) for value in values):
            unknown = sorted(set(values) - source_ids)
            if unknown:
                errors.append(f"{label} has unknown source ids: {', '.join(unknown)}")
        if type(item.get("stage")) is not int or item["stage"] not in range(
            -1, len(INTERVAL_DAYS)
        ):
            errors.append(f"{label} has invalid stage: {item.get('stage')}")
        try:
            parse_time(item["due_at"])
        except (KeyError, StateError) as error:
            errors.append(f"{label} has invalid due_at: {error}")
        reviewed = item.get("last_reviewed_at")
        if reviewed is not None:
            try:
                parse_time(reviewed)
            except StateError as error:
                errors.append(f"{label} has invalid last_reviewed_at: {error}")
        if item.get("last_rating") is not None and item.get("last_rating") not in RATINGS:
            errors.append(f"{label} has invalid last_rating: {item.get('last_rating')}")
    return errors


def event_errors(events, path, item_ids):
    errors = []
    for index, event in enumerate(events, 1):
        label = f"event {index} in {path}"
        if not isinstance(event, dict):
            errors.append(f"{label} must be an object")
            continue
        try:
            parse_time(event["reviewed_at"])
        except (KeyError, StateError) as error:
            errors.append(f"{label} has invalid reviewed_at: {error}")
        item_id = event.get("item_id")
        if not isinstance(item_id, str) or item_id not in item_ids:
            errors.append(f"{label} has unknown item_id: {event.get('item_id')}")
        if event.get("rating") not in RATINGS:
            errors.append(f"{label} has invalid rating: {event.get('rating')}")
        confidence = event.get("confidence")
        if type(confidence) is not int or not 1 <= confidence <= 5:
            errors.append(f"{label} has invalid confidence: {confidence}")
        if not isinstance(event.get("evidence"), str) or not event["evidence"].strip():
            errors.append(f"{label} evidence must be non-empty text")
        stage = event.get("next_stage")
        if type(stage) is not int or stage not in range(len(INTERVAL_DAYS)):
            errors.append(f"{label} has invalid next_stage: {stage}")
        try:
            parse_time(event["next_due_at"])
        except (KeyError, StateError) as error:
            errors.append(f"{label} has invalid next_due_at: {error}")
    return errors


def event_transition_errors(events, path):
    errors = []
    stages = {}
    previous_time = None
    for index, event in enumerate(events, 1):
        if not isinstance(event, dict):
            continue
        item_id = event.get("item_id")
        rating = event.get("rating")
        try:
            reviewed_at = parse_time(event["reviewed_at"])
        except (KeyError, StateError):
            continue
        if previous_time is not None and reviewed_at < previous_time:
            errors.append(f"event {index} in {path} is earlier than the previous event")
        previous_time = reviewed_at
        if not isinstance(item_id, str) or rating not in RATINGS:
            continue
        expected_stage, expected_due_at = next_schedule(
            stages.get(item_id, -1), rating, reviewed_at
        )
        if (
            event.get("next_stage") != expected_stage
            or event.get("next_due_at") != format_time(expected_due_at)
        ):
            errors.append(f"event {index} in {path} has an invalid transition")
        stages[item_id] = expected_stage
    return errors


def dependency_history_errors(events, objectives, path):
    errors = []
    ratings = {}
    for index, event in enumerate(events, 1):
        if not isinstance(event, dict):
            continue
        item_id = event.get("item_id")
        objective = objectives.get(item_id)
        if objective is None:
            continue
        blockers = [
            dependency
            for dependency in objective["depends_on"]
            if ratings.get(dependency) not in ("good", "easy")
        ]
        if blockers:
            errors.append(
                f"event {index} in {path} precedes ready dependencies: {', '.join(blockers)}"
            )
        if event.get("rating") in RATINGS:
            ratings[item_id] = event["rating"]
    return errors


def event_mastery_errors(events, mastery, path):
    if not isinstance(mastery, dict) or not isinstance(mastery.get("items"), list):
        return []
    items = {
        item.get("id"): item
        for item in mastery["items"]
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    latest = {}
    for event in events:
        if isinstance(event, dict) and isinstance(event.get("item_id"), str):
            latest[event["item_id"]] = event
    errors = []
    for item_id, event in latest.items():
        item = items.get(item_id)
        if item is None:
            continue
        expected = {
            "stage": event.get("next_stage"),
            "due_at": event.get("next_due_at"),
            "last_reviewed_at": event.get("reviewed_at"),
            "last_rating": event.get("rating"),
        }
        if any(item.get(field) != value for field, value in expected.items()):
            errors.append(f"item {item_id} does not match latest event in {path}")
    for item_id, item in items.items():
        if item_id not in latest and (
            item.get("stage") != -1
            or item.get("last_reviewed_at") is not None
            or item.get("last_rating") is not None
        ):
            errors.append(f"item {item_id} has invalid initial review state in {path}")
    return errors


def validate_subject_state(home, subject_id):
    path = subject_path(home, subject_id)
    errors = []
    for name in SUBJECT_FILES:
        if not (path / name).is_file():
            errors.append(f"missing subject file: {path / name}")

    mission = path / "MISSION.md"
    if mission.is_file():
        try:
            errors.extend(mission_errors(mission))
        except OSError as error:
            errors.append(str(error))

    sources = {}
    resources = path / "RESOURCES.md"
    if resources.is_file():
        try:
            sources = read_sources(resources)
            if not sources:
                errors.append(f"subject {subject_id} requires at least one source in {resources}")
        except (OSError, StateError) as error:
            errors.append(str(error))

    objectives = {}
    plan = path / "PLAN.md"
    if plan.is_file():
        try:
            objectives = read_objectives(plan)
            if not objectives:
                errors.append(f"subject {subject_id} requires at least one objective in {plan}")
        except (OSError, StateError) as error:
            errors.append(str(error))

    mastery = None
    mastery_path = path / "mastery.json"
    if mastery_path.is_file():
        try:
            mastery = read_json(mastery_path)
            errors.extend(mastery_errors(mastery, mastery_path, set(sources)))
            if isinstance(mastery, dict) and isinstance(mastery.get("items"), list):
                if not mastery["items"]:
                    errors.append(f"subject {subject_id} requires at least one retrieval item")
                for item in mastery["items"]:
                    if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                        continue
                    if item["id"] not in objectives:
                        errors.append(
                            f"item {item['id']} is not an objective in {plan}"
                        )
        except (OSError, StateError) as error:
            errors.append(str(error))

    events = []
    events_path = path / "events.jsonl"
    if events_path.is_file():
        try:
            events = read_events(events_path)
            item_ids = {
                item.get("id")
                for item in mastery.get("items", [])
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            } if isinstance(mastery, dict) else set()
            errors.extend(event_errors(events, events_path, item_ids))
            errors.extend(event_transition_errors(events, events_path))
            errors.extend(dependency_history_errors(events, objectives, events_path))
            errors.extend(event_mastery_errors(events, mastery, events_path))
        except (OSError, StateError) as error:
            errors.append(str(error))

    return {
        "sources": sources,
        "objectives": objectives,
        "mastery": mastery,
        "events": events,
    }, errors


def command_validate(args):
    home = resolve_home(args.home)
    registry = load_registry(home)
    if args.activate and not args.subject:
        raise StateError("--activate requires --subject")
    errors = []
    subjects = registry["subjects"]
    if args.subject:
        require_identifier(args.subject, "subject id")
        subjects = [find_subject(registry, args.subject)]
    for subject in subjects:
        _, subject_errors = validate_subject_state(home, subject["id"])
        errors.extend(subject_errors)
    if errors:
        raise StateError("\n".join(errors))
    if args.activate:
        subjects[0]["ready"] = True
        write_json(registry_path(home), registry)
    emit(
        {
            "valid": True,
            "subjects": len(subjects),
            "activated": args.subject if args.activate else None,
        }
    )


def build_parser():
    parser = argparse.ArgumentParser(prog="state.py")
    parser.add_argument("--home")
    commands = parser.add_subparsers(dest="command", required=True)

    status = commands.add_parser("status")
    status.add_argument("--now")
    status.set_defaults(handler=command_status)

    initialize = commands.add_parser("init-subject")
    initialize.add_argument("--id", required=True)
    initialize.add_argument("--title", required=True)
    initialize.add_argument("--mission", required=True)
    initialize.add_argument("--cue", action="append", default=[])
    initialize.set_defaults(handler=command_init_subject)

    add_item = commands.add_parser("add-item")
    add_item.add_argument("--subject", required=True)
    add_item.add_argument("--id", required=True)
    add_item.add_argument("--objective", required=True)
    add_item.add_argument("--prompt", required=True)
    add_item.add_argument("--criterion", action="append", default=[])
    add_item.add_argument("--concept", action="append", default=[])
    add_item.add_argument("--source", action="append", default=[])
    add_item.add_argument("--due-at", required=True)
    add_item.set_defaults(handler=command_add_item)

    review = commands.add_parser("record-review")
    review.add_argument("--subject", required=True)
    review.add_argument("--item", required=True)
    review.add_argument("--rating", choices=RATINGS, required=True)
    review.add_argument("--confidence", type=int, required=True)
    review.add_argument("--evidence", required=True)
    review.add_argument("--now")
    review.set_defaults(handler=command_record_review)

    enabled = commands.add_parser("set-enabled")
    enabled.add_argument("--subject")
    selection = enabled.add_mutually_exclusive_group(required=True)
    selection.add_argument("--enabled", action="store_true")
    selection.add_argument("--disabled", action="store_true")
    enabled.set_defaults(handler=command_set_enabled)

    validate = commands.add_parser("validate")
    validate.add_argument("--subject")
    validate.add_argument("--activate", action="store_true")
    validate.set_defaults(handler=command_validate)
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "set-enabled":
        args.enabled = not args.disabled
    try:
        args.handler(args)
    except (OSError, StateError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
