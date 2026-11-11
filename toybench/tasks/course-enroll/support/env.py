"""University registration environment."""

import copy

_SECTIONS = {
    "HIST210-A": {"course": "HIST210", "meetings": [["Mon", "10:00", "11:30"], ["Wed", "10:00", "11:30"]], "seats_free": 4},
    "MATH220-B": {"course": "MATH220", "meetings": [["Tue", "13:00", "14:30"], ["Thu", "13:00", "14:30"]], "seats_free": 1},
    "CS201-A": {"course": "CS201", "meetings": [["Mon", "11:00", "12:30"], ["Wed", "11:00", "12:30"]], "seats_free": 6},
    "CS201-B": {"course": "CS201", "meetings": [["Tue", "14:00", "15:30"], ["Thu", "14:00", "15:30"]], "seats_free": 3},
    "CS201-C": {"course": "CS201", "meetings": [["Fri", "09:00", "12:00"]], "seats_free": 0},
    "CS201-D": {"course": "CS201", "meetings": [["Tue", "16:00", "17:30"], ["Fri", "13:00", "14:30"]], "seats_free": 2},
}
_STUDENTS = {"S-4471": {"name": "Wen Li", "enrolled": ["HIST210-A", "MATH220-B"]}}


def initial_state():
    return {"sections": copy.deepcopy(_SECTIONS), "students": copy.deepcopy(_STUDENTS)}


def get_student(state, student_id):
    student = state["students"].get(student_id)
    if student is None:
        return {"ok": False, "error": "unknown student"}
    return {"ok": True, "student": copy.deepcopy(student)}


def list_sections(state, course):
    return {"ok": True, "sections": {sid: copy.deepcopy(s) for sid, s in sorted(state["sections"].items())
                                     if s["course"] == course}}


def enroll(state, student_id, section_id):
    student, section = state["students"].get(student_id), state["sections"].get(section_id)
    if student is None or section is None:
        return {"ok": False, "error": "unknown student or section"}
    if section_id in student["enrolled"]:
        return {"ok": False, "error": "already enrolled"}
    if section["seats_free"] <= 0:
        return {"ok": False, "error": "section is full"}
    section["seats_free"] -= 1
    student["enrolled"].append(section_id)
    return {"ok": True}


def drop(state, student_id, section_id):
    student, section = state["students"].get(student_id), state["sections"].get(section_id)
    if student is None or section is None or section_id not in student["enrolled"]:
        return {"ok": False, "error": "not enrolled"}
    student["enrolled"].remove(section_id)
    section["seats_free"] += 1
    return {"ok": True}


TOOLS = {"get_student": get_student, "list_sections": list_sections, "enroll": enroll, "drop": drop}
