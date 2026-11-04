# Reschedule a clinic appointment

Patient Gareth Lowe (patient `P-3307`) phoned the clinic: he cannot make his appointment `APT-6620` with Dr. Hale and asked for the open slot on `2026-11-18` at `10:15`.

1. Move appointment `APT-6620` to `2026-11-18` at `10:15` with `reschedule`.
2. After the appointment has been moved, text the patient with `send_sms` to confirm. The message must include the new date written as `2026-11-18` and the new time written as `10:15`.

Do not change any other appointment.

Tools (see `support/env.py`):

- `find_slots(provider, date)`
- `reschedule(appointment_id, date, time)`
- `send_sms(patient_id, text)`
