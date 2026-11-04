# Enroll a student in a course section

Student `S-4471` needs to take CS201 this term. Enroll the student in exactly one section of `CS201` that has a free seat and whose meeting times do not overlap any section the student is already enrolled in. Keep the student's existing enrollments.

Two meetings overlap when they are on the same day and their time ranges intersect.

Tools (see `support/env.py`):

- `get_student(student_id)`: current enrollments
- `list_sections(course)`: sections with meeting times and free seats
- `enroll(student_id, section_id)`
- `drop(student_id, section_id)`
