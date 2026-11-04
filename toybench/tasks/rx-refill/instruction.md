# Refill a prescription

Patient `P-5512` asks to refill her atorvastatin prescription for pickup at the Elm Street pharmacy.

1. Request a refill of prescription `RX-1001` at pharmacy `PH-ELM` with `request_refill`.
2. Then notify the patient with `notify_patient`. The message must include the pharmacy name `Elm Street` and the prescription number `RX-1001`.

Do not request refills of any other prescription.

Tools (see `support/env.py`):

- `list_prescriptions(patient_id)`
- `list_pharmacies()`
- `request_refill(rx_id, pharmacy_id)`
- `notify_patient(patient_id, message)`
