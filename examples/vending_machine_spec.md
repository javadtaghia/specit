# Smart Vending Machine (SVM) — Operational Concept Description (V1)

## 1. Overview & Systems

The Smart Vending Machine (SVM) sells snacks and chilled beverages via a touchscreen keypad, contactless card terminal, coin/bill acceptor, motorized spiral dispenser with drop sensor, and cloud telemetry backend.

| System / Component | Responsibility |
| --- | --- |
| Vending Controller (SVM) | Orchestrates selection, pricing, payment authorization, motor actuation, drop verification, inventory counts, and fault alarms. |
| Payment Gateway (PGW) | Authorizes contactless card/tap payments and settles captured transactions. |
| Cash Module (CASH) | Validates coins/notes, tracks inserted balance, and dispenses change. |
| Dispenser Hardware (DISP) | Drives slot spiral motor and monitors infrared drop sensor. |
| Operations Portal (OPS) | Displays live stock levels, sales telemetry, temperature alarms, and restock tasks for field technicians. |

## 2. Actors
- **Customer**: Browses items, selects a slot, pays by card or cash, collects item and change.
- **Service Technician**: Restocks slots, updates slot prices/expiry dates, clears dispenser jams, and refills coin tubes.

## 3. Core Operational Processes

### 3.1 Product Selection & Dispensing (VM-001)
1. Customer enters a slot code (e.g. A1) on the keypad or touchscreen.
2. SVM checks slot stock quantity (> 0), slot health (not jammed/locked), and temperature compliance for chilled items.
3. SVM displays item name and price and requests payment (`RequestPayment`).
4. Once `PaymentAuthorized` is received, SVM sends `ActuateSpiral` to DISP.
5. DISP turns the spiral and monitors the infrared drop sensor (`DropConfirmed` within 5 seconds).
6. On `DropConfirmed`, SVM decrements slot inventory by 1, sends `CapturePayment` (or dispenses cash change), and publishes `SaleRecorded` to OPS.

**Exceptions:**
- **Out of stock or jammed slot**: Reject selection immediately with reason message; do not request payment.
- **No drop detected (jam / vend failure)**: Do not charge customer — send `VoidPayment` (or refund full inserted cash), mark slot `JAMMED`, and emit `SlotFaultAlarm` to OPS.
- **Chilled cabinet over-temperature (> 8°C for 30 minutes)**: Lock perishable beverage slots (`TEMP_LOCKED`) and alert OPS.

### 3.2 Payment & Change Handling (VM-002)
1. Customer either taps a contactless card (PGW) or inserts coins/notes (CASH).
2. For card payments, SVM requests a pre-authorization (`AuthorizeCard`) for the exact item price; final capture happens only after `DropConfirmed`.
3. For cash payments, SVM accumulates inserted credit until credit >= item price; customer may press Cancel before dispensing to receive full refund (`RefundCash`).
4. After `DropConfirmed`, SVM computes change (`credit - price`) and commands `DispenseChange`.

**Exceptions:**
- **Card declined or gateway timeout**: Display decline reason and return to idle without actuating dispenser.
- **Insufficient change in coin tubes**: Display "Exact change only" warning before accepting cash; exact policy for partial-change failure is open.
- **Duplicate payment confirmation message**: Must be idempotent; never dispense two items for one transaction ID.

### 3.3 Restocking & Maintenance Clearing (VM-003)
1. Technician authenticates via service RFID badge or PIN to enter `SERVICE_MODE`.
2. SVM pauses customer sales while door is open (`DoorOpened`).
3. Technician clears any jammed spirals, replenishes slot quantities, updates coin tube levels, and verifies cabinet cooling.
4. Technician confirms inventory update (`SubmitRestockCount`) and closes the door (`DoorClosed`).
5. SVM runs a quick self-check, clears resolved faults, returns to `IDLE`, and syncs updated stock (`InventorySynced`) to OPS.

**Exceptions:**
- **Unauthenticated door open**: Trigger `TamperAlarm` immediately to OPS and disable dispensing.
- **Restock count exceeds physical slot capacity**: Reject entry and prompt technician to correct quantity.

## 4. Non-Functional Requirements
- **Reliability**: Payment capture must never occur without a confirmed physical drop (`DropConfirmed`).
- **Offline resilience**: Cash purchases must continue working when cloud connectivity to OPS is down; sales events queue locally until reconnected.
- **Audit**: Every stock change, fault, refund, and service visit must be logged with timestamp and actor.

## 5. Open Questions
- **O-01**: Maximum retry count on spiral motor before declaring a jam (1 retry vs immediate refund)?
- **O-02**: Should multi-item cart purchases be supported in V1 or strictly single-item vends?
- **O-03**: Offline contactless card floor limit — permitted or card disabled when PGW is unreachable?

## 6. Out of Scope for V1
- Loyalty points and mobile app pre-ordering.
- Dynamic surge pricing based on ambient temperature.
