"""Seed a realistic, 100% source-grounded Smart Vending Machine demo project and record an HD walkthrough video."""
import shutil
import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from engine.diagrams import extract_mermaid_blocks, mermaid_to_drawio_xml
from engine.git_sync import connect_git, commit_project
from engine.model import Artifact, Catalogue, Evidence, Foundation, GlossaryItem, Planning, Process, QualityReport, Rule, SystemItem
from engine.pipeline import quality_checks
from engine.sources import parse_source
from engine.storage import Store

ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = ROOT / 'examples' / 'vending_machine_spec.md'
DEMO_DIR = ROOT / 'demo'
PROJECT_SLUG = 'vending-machine-demo'


def seed_vending_project() -> Path:
    store = Store(str(ROOT / 'workspace'))
    proj_dir = store.root / PROJECT_SLUG
    if proj_dir.exists():
        shutil.rmtree(proj_dir)
    p = store.project(PROJECT_SLUG)

    raw_bytes = SPEC_PATH.read_bytes()
    store.save_upload(p, SPEC_PATH.name, raw_bytes)
    src = parse_source(SPEC_PATH.name, raw_bytes)
    sid = src['source_id']
    loc1 = src['chunks'][0]['locator']
    loc2 = src['chunks'][-1]['locator']

    cat = Catalogue(
        project_name='Smart Vending Machine (SVM)',
        project_summary=(
            'Automated snack and chilled beverage vending controller orchestrating slot selection, '
            'contactless & cash payment authorization, spiral dispensing with infrared drop verification, '
            'and technician restocking with cloud telemetry.'
        ),
        shared_actors=['Customer', 'Service Technician', 'Vending Controller (SVM)', 'Payment Gateway (PGW)', 'Cash Module (CASH)', 'Dispenser Hardware (DISP)', 'Operations Portal (OPS)'],
        systems=[
            SystemItem(name='Vending Controller (SVM)', responsibility='Orchestrates selection, pricing, payment authorization, motor actuation, drop verification, inventory counts, and fault alarms.', ownership='Core System'),
            SystemItem(name='Payment Gateway (PGW)', responsibility='Authorizes contactless card payments and settles captured transactions.', ownership='External'),
            SystemItem(name='Cash Module (CASH)', responsibility='Validates coins/notes, tracks inserted credit, and dispenses change.', ownership='Hardware Peripheral'),
            SystemItem(name='Dispenser Hardware (DISP)', responsibility='Drives slot spiral motor and monitors infrared drop sensor.', ownership='Hardware Peripheral'),
            SystemItem(name='Operations Portal (OPS)', responsibility='Displays live stock levels, sales telemetry, temperature alarms, and restock tasks.', ownership='Cloud Backend'),
        ],
        glossary=[
            GlossaryItem(term='SVM', definition='Smart Vending Machine controller'),
            GlossaryItem(term='PGW', definition='Contactless Payment Gateway'),
            GlossaryItem(term='DISP', definition='Motorized spiral dispenser and infrared drop sensor'),
            GlossaryItem(term='OPS', definition='Cloud Operations & Telemetry Portal'),
        ],
        nfrs=[
            'Reliability: Payment capture must never occur without a confirmed physical drop (DropConfirmed).',
            'Offline resilience: Cash purchases continue working when cloud connectivity to OPS is down; events queue locally.',
            'Audit: Every stock change, fault, refund, and service visit is logged with timestamp and actor.',
        ],
        exclusions=[
            'Loyalty points and mobile app pre-ordering (out of scope for V1).',
            'Dynamic surge pricing based on ambient temperature (out of scope for V1).',
        ],
        open_questions=[
            'O-01: Maximum retry count on spiral motor before declaring a jam (1 retry vs immediate refund)?',
            'O-02: Should multi-item cart purchases be supported in V1 or strictly single-item vends?',
            'O-03: Offline contactless card floor limit — permitted or card disabled when PGW is unreachable?',
        ],
        processes=[
            Process(
                id='VM-001',
                name='Product Selection & Dispensing',
                description='Customer selects a slot, pays, and receives a drop-verified product while SVM updates inventory and telemetry.',
                actors=['Customer', 'Vending Controller (SVM)', 'Dispenser Hardware (DISP)', 'Payment Gateway (PGW)', 'Operations Portal (OPS)'],
                trigger='Customer enters a slot code (e.g. A1) on keypad or touchscreen.',
                inputs=['SlotCode', 'SlotStock', 'CabinetTemperature', 'PaymentAuthorized'],
                outputs=['DropConfirmed', 'CapturePayment', 'SaleRecorded', 'SlotFaultAlarm'],
                steps=[
                    'Customer enters slot code (e.g. A1) on keypad or touchscreen.',
                    'SVM validates slot stock > 0, slot health (not jammed), and chilled temperature compliance.',
                    'SVM displays item name and price and emits RequestPayment.',
                    'On PaymentAuthorized, SVM sends ActuateSpiral command to DISP.',
                    'DISP rotates spiral and waits up to 5 seconds for infrared DropConfirmed.',
                    'On DropConfirmed, SVM decrements stock, captures payment (or dispenses change), and publishes SaleRecorded to OPS.',
                ],
                exceptions=[
                    'Out of stock or jammed slot: reject selection immediately without requesting payment.',
                    'No drop detected within 5s: void payment or refund cash, mark slot JAMMED, emit SlotFaultAlarm.',
                    'Chilled cabinet > 8°C for 30 min: lock perishable slots (TEMP_LOCKED) and alert OPS.',
                ],
                messages=['RequestPayment', 'PaymentAuthorized', 'ActuateSpiral', 'DropConfirmed', 'CapturePayment', 'VoidPayment', 'SaleRecorded', 'SlotFaultAlarm'],
                entities=['Slot', 'Product', 'VendTransaction', 'TemperatureReading'],
                rules=[
                    Rule(id='VM-001-R1', statement='Payment capture must never occur without a confirmed physical drop (DropConfirmed).', classification='source_defined', evidence=[Evidence(source_id=sid, locator=loc2, quote='Payment capture must never occur without a confirmed physical drop')]),
                    Rule(id='VM-001-R2', statement='Chilled cabinet over 8°C for 30 minutes locks perishable slots.', classification='source_defined', evidence=[Evidence(source_id=sid, locator=loc1, quote='Chilled cabinet over-temperature (> 8°C for 30 minutes)')]),
                    Rule(id='VM-001-R3', statement='Maximum spiral motor retry count before declaring jam is unresolved (O-01).', classification='unresolved'),
                ],
                open_questions=['O-01: 1 spiral retry vs immediate refund on jam?'],
                evidence=[Evidence(source_id=sid, locator=loc1, quote='3.1 Product Selection & Dispensing (VM-001)')],
                confidence='high',
            ),
            Process(
                id='VM-002',
                name='Payment & Change Handling',
                description='Handles contactless card pre-authorization/capture and cash credit accumulation, cancellation refund, and change dispensing.',
                actors=['Customer', 'Vending Controller (SVM)', 'Payment Gateway (PGW)', 'Cash Module (CASH)'],
                trigger='SVM displays item price and emits RequestPayment.',
                inputs=['CardTap', 'CoinsOrNotes', 'CancelRequest', 'DropConfirmed'],
                outputs=['PaymentAuthorized', 'CapturePayment', 'VoidPayment', 'DispenseChange', 'RefundCash'],
                steps=[
                    'Customer chooses contactless card (PGW) or inserts coins/notes (CASH).',
                    'For card: SVM sends AuthorizeCard pre-authorization for exact item price.',
                    'For cash: CASH accumulates inserted balance until balance >= item price.',
                    'If Customer presses Cancel before dispensing, CASH returns full inserted balance (RefundCash).',
                    'After DropConfirmed, SVM sends CapturePayment (card) or DispenseChange (cash).',
                ],
                exceptions=[
                    'Card declined or gateway timeout: show decline reason and return to IDLE without actuating dispenser.',
                    'Insufficient change in coin tubes: show Exact change only warning before cash acceptance.',
                    'Duplicate payment confirmation: idempotent handling by transaction ID — never double-dispense.',
                ],
                messages=['AuthorizeCard', 'PaymentAuthorized', 'CapturePayment', 'VoidPayment', 'RefundCash', 'DispenseChange'],
                entities=['PaymentSession', 'CashLedger', 'CoinTube'],
                rules=[
                    Rule(id='VM-002-R1', statement='Duplicate payment confirmation messages must be idempotent and never dispense two items.', classification='source_defined', evidence=[Evidence(source_id=sid, locator=loc1, quote='Must be idempotent; never dispense two items for one transaction ID.')]),
                    Rule(id='VM-002-R2', statement='Offline contactless card floor limit policy is unresolved (O-03).', classification='unresolved'),
                ],
                open_questions=['O-03: Permit offline card floor limit or disable card when PGW unreachable?'],
                evidence=[Evidence(source_id=sid, locator=loc1, quote='3.2 Payment & Change Handling (VM-002)')],
                confidence='high',
            ),
            Process(
                id='VM-003',
                name='Restocking & Maintenance Clearing',
                description='Service technician authenticates, clears jams, replenishes stock and coin tubes, and syncs inventory to OPS.',
                actors=['Service Technician', 'Vending Controller (SVM)', 'Dispenser Hardware (DISP)', 'Cash Module (CASH)', 'Operations Portal (OPS)'],
                trigger='Technician presents RFID service badge or enters PIN.',
                inputs=['ServiceCredential', 'DoorOpened', 'SubmitRestockCount', 'DoorClosed'],
                outputs=['InventorySynced', 'TamperAlarm'],
                steps=[
                    'Technician authenticates via RFID badge or PIN to enter SERVICE_MODE.',
                    'SVM pauses customer sales upon DoorOpened.',
                    'Technician clears jammed spirals, restocks slots, refills coin tubes, and checks cooling.',
                    'Technician submits updated slot counts (SubmitRestockCount) and closes door (DoorClosed).',
                    'SVM runs self-check, clears resolved faults, returns to IDLE, and publishes InventorySynced to OPS.',
                ],
                exceptions=[
                    'Unauthenticated door open: immediately emit TamperAlarm to OPS and disable dispensing.',
                    'Restock count exceeds physical slot capacity: reject count and prompt correction.',
                ],
                messages=['DoorOpened', 'SubmitRestockCount', 'DoorClosed', 'InventorySynced', 'TamperAlarm'],
                entities=['ServiceSession', 'StockAdjustment', 'Alarm'],
                rules=[
                    Rule(id='VM-003-R1', statement='Unauthenticated door open triggers immediate TamperAlarm and disables dispensing.', classification='source_defined', evidence=[Evidence(source_id=sid, locator=loc2, quote='Trigger TamperAlarm immediately to OPS and disable dispensing.')]),
                ],
                open_questions=[],
                evidence=[Evidence(source_id=sid, locator=loc2, quote='3.3 Restocking & Maintenance Clearing (VM-003)')],
                confidence='high',
            ),
        ],
    )

    # Create two revisions so Revision Diff looks awesome in the video!
    cat_v1 = cat.model_copy(deep=True)
    cat_v1.open_questions = cat.open_questions[:2]
    store.write(p, 'catalogue', cat_v1.model_dump(), 'initial extraction from vending_machine_spec.md')
    store.write(p, 'catalogue', cat.model_dump(), 'added O-03 offline card policy question during review')
    store.write(p, 'catalogue_approved', True, 'human approved catalogue')

    # Rich 4 artifacts for VM-001, VM-002, VM-003
    vm1 = Artifact(
        process_id='VM-001',
        workflow_md=(
            '# VM-001 — Product Selection & Dispensing\n\n'
            '**Objective:** Safely guide a customer from slot selection through payment authorization, spiral actuation, infrared drop verification, and inventory/telemetry update.\n\n'
            '## Operational Flow\n\n'
            '```mermaid\n'
            'flowchart LR\n'
            '  Customer["Customer | selects slot A1"]\n'
            '  SVM["Vending Controller | validates stock & temp"]\n'
            '  PGW["Payment Gateway | authorize / capture"]\n'
            '  DISP["Dispenser | spiral + IR drop sensor"]\n'
            '  OPS["Operations Portal | live stock & alarms"]\n\n'
            '  Customer -->|SlotCode A1| SVM\n'
            '  SVM -->|RequestPayment| PGW\n'
            '  PGW -->|PaymentAuthorized| SVM\n'
            '  SVM -->|ActuateSpiral| DISP\n'
            '  DISP -->|DropConfirmed < 5s| SVM\n'
            '  SVM -->|SaleRecorded| OPS\n\n'
            '  subgraph VendCore[SVM Execution Boundary]\n'
            '    SVM\n'
            '    DISP\n'
            '  end\n'
            '```\n\n'
            '## Primary Steps (`SOURCE_DEFINED`)\n\n'
            '1. Customer enters a slot code (e.g. `A1`) on the keypad or touchscreen.\n'
            '2. SVM validates slot stock `> 0`, slot health (`AVAILABLE`), and chilled temperature compliance (`<= 8°C`).\n'
            '3. SVM displays price and initiates `RequestPayment`.\n'
            '4. Upon `PaymentAuthorized`, SVM commands `ActuateSpiral` on `DISP`.\n'
            '5. `DISP` rotates the spiral and monitors the infrared drop sensor for `DropConfirmed` within 5 seconds.\n'
            '6. SVM decrements stock, sends `CapturePayment` (or dispenses change), and publishes `SaleRecorded` to `OPS`.\n\n'
            '## Key Exceptions & Safety Rules\n\n'
            '| Exception | Mandatory Behaviour | Classification |\n'
            '| --- | --- | --- |\n'
            '| Out of stock or jammed slot | Reject immediately; do not initiate payment | `SOURCE_DEFINED` |\n'
            '| No drop detected within 5s | Send `VoidPayment` / refund cash; mark slot `JAMMED`; emit `SlotFaultAlarm` | `SOURCE_DEFINED` |\n'
            '| Cabinet > 8°C for 30 min | Lock chilled slots (`TEMP_LOCKED`) and alert OPS | `SOURCE_DEFINED` |\n'
            '| Motor retry before jam | Unresolved (`O-01`: 1 retry vs immediate refund) | `UNRESOLVED` |\n'
        ),
        boundaries_md=(
            '# VM-001 — System Boundaries & Ownership\n\n'
            'Defines strict ownership between the embedded **Vending Controller (SVM)**, external **Payment Gateway (PGW)**, hardware peripherals (**DISP**, **CASH**), and cloud **Operations Portal (OPS)**.\n\n'
            '```mermaid\n'
            'flowchart TB\n'
            '  Customer["Customer | touchscreen UI"]\n'
            '  PGW["Payment Gateway | card auth & settlement"]\n'
            '  OPS["Operations Portal | cloud telemetry"]\n\n'
            '  subgraph MachineBoundary[Physical Machine Boundary]\n'
            '    SVM["Vending Controller | state & ledger"]\n'
            '    DISP["Dispenser Hardware | motor & IR sensor"]\n'
            '    CASH["Cash Module | coin & bill acceptor"]\n'
            '    SVM -->|ActuateSpiral| DISP\n'
            '    SVM -->|DispenseChange| CASH\n'
            '  end\n\n'
            '  Customer -->|Select slot| SVM\n'
            '  SVM -->|Authorize / Capture| PGW\n'
            '  SVM -->|Outbox telemetry| OPS\n'
            '```\n\n'
            '## Interface Register\n\n'
            '| Message | Direction | Idempotency Rule |\n'
            '| --- | --- | --- |\n'
            '| `AuthorizeCard` / `CapturePayment` | SVM → PGW | Keyed by `transactionId`; capture only after `DropConfirmed` |\n'
            '| `ActuateSpiral` / `DropConfirmed` | SVM ↔ DISP | Single actuation per `vendId`; 5-second sensor timeout |\n'
            '| `SaleRecorded` / `SlotFaultAlarm` | SVM → OPS | Queued locally in durable outbox when cloud is offline |\n'
        ),
        domain_md=(
            '# VM-001 — Domain Model & Invariants\n\n'
            'Separates physical slot state (`Slot`) from commercial execution (`VendTransaction`) so hardware jams and payment settlement never lose consistency.\n\n'
            '```mermaid\n'
            'classDiagram\n'
            '  direction LR\n'
            '  class Slot {\n'
            '    slotCode\n'
            '    quantity\n'
            '    capacity\n'
            '    healthStatus\n'
            '  }\n'
            '  class Product {\n'
            '    sku\n'
            '    name\n'
            '    priceCents\n'
            '    chilledRequired\n'
            '  }\n'
            '  class VendTransaction {\n'
            '    transactionId\n'
            '    state\n'
            '    paymentMethod\n'
            '    amountCents\n'
            '  }\n'
            '  Slot "1" --> "1" Product : holds\n'
            '  VendTransaction "*" --> "1" Slot : dispensesFrom\n'
            '```\n\n'
            '## Core Invariants (`DESIGN_PROPOSED` grounded in OCD)\n\n'
            '- `Slot.quantity` is always `0 <= quantity <= capacity`.\n'
            '- A `VendTransaction` cannot transition to `CAPTURED` without an attached `DropConfirmed` hardware event.\n'
            '- When `CabinetTemperature > 8°C` for 30 minutes, every `Slot` holding a `Product` with `chilledRequired = true` transitions to `TEMP_LOCKED`.\n'
        ),
        states_md=(
            '# VM-001 — Vend Transaction State Machine\n\n'
            'Guarantees zero ghost charges: funds are only captured after physical infrared drop confirmation.\n\n'
            '```mermaid\n'
            'stateDiagram-v2\n'
            '  [*] --> IDLE\n'
            '  IDLE --> AWAITING_PAYMENT : SlotSelected\n'
            '  AWAITING_PAYMENT --> DISPENSING : PaymentAuthorized\n'
            '  AWAITING_PAYMENT --> IDLE : CancelledOrDeclined\n'
            '  DISPENSING --> COMPLETED : DropConfirmed\n'
            '  DISPENSING --> REFUNDED : DropTimeoutJam\n'
            '  COMPLETED --> [*]\n'
            '  REFUNDED --> [*]\n'
            '```\n\n'
            '## Transition Table\n\n'
            '| From | Event | Guard | To | Side Effect |\n'
            '| --- | --- | --- | --- | --- |\n'
            '| `IDLE` | `SlotSelected` | `stock > 0 && health == AVAILABLE` | `AWAITING_PAYMENT` | Emit `RequestPayment` |\n'
            '| `AWAITING_PAYMENT` | `PaymentAuthorized` | Valid unique `transactionId` | `DISPENSING` | Send `ActuateSpiral` |\n'
            '| `DISPENSING` | `DropConfirmed` | Received within 5s | `COMPLETED` | Decrement stock, `CapturePayment`, queue `SaleRecorded` |\n'
            '| `DISPENSING` | `DropTimeoutJam` | 5s elapsed without drop | `REFUNDED` | Send `VoidPayment`/`RefundCash`, mark slot `JAMMED`, emit `SlotFaultAlarm` |\n'
        ),
    )

    vm2 = Artifact(
        process_id='VM-002',
        workflow_md=(
            '# VM-002 — Payment & Change Handling\n\n'
            '**Objective:** Coordinate card pre-authorization/capture and cash credit/change dispensing with strict idempotency.\n\n'
            '```mermaid\n'
            'flowchart LR\n'
            '  Customer["Customer | tap card or insert cash"]\n'
            '  SVM["Vending Controller | transaction ledger"]\n'
            '  PGW["Payment Gateway | pre-auth & capture"]\n'
            '  CASH["Cash Module | credit & coin tubes"]\n\n'
            '  Customer -->|Card tap| PGW\n'
            '  Customer -->|Coins / notes| CASH\n'
            '  PGW -->|PaymentAuthorized| SVM\n'
            '  CASH -->|CreditReached| SVM\n'
            '  SVM -->|CapturePayment / DispenseChange| Customer\n'
            '```\n\n'
            '## Rules\n\n'
            '- **Idempotency (`SOURCE_DEFINED`)**: Duplicate `PaymentAuthorized` events with the same `transactionId` are ignored.\n'
            '- **Pre-auth before vend (`SOURCE_DEFINED`)**: Card capture happens strictly after `DropConfirmed`.\n'
            '- **Exact Change Warning (`SOURCE_DEFINED`)**: Warn customer before cash insertion when coin tubes are low.\n'
        ),
        boundaries_md=(
            '# VM-002 — Payment Boundaries\n\n'
            '```mermaid\n'
            'flowchart LR\n'
            '  SVM[Vending Controller] -->|AuthorizeCard / Capture / Void| PGW[Payment Gateway]\n'
            '  SVM -->|AcceptCash / Refund / Change| CASH[Cash Module]\n'
            '```\n\n'
            'SVM never stores raw card PAN data; PGW owns all PCI card tokenization and settlement.\n'
        ),
        domain_md=(
            '# VM-002 — Payment Domain Model\n\n'
            '```mermaid\n'
            'classDiagram\n'
            '  direction LR\n'
            '  class PaymentSession {\n'
            '    transactionId\n'
            '    method\n'
            '    authorizedCents\n'
            '    status\n'
            '  }\n'
            '  class CoinTube {\n'
            '    denominationCents\n'
            '    coinCount\n'
            '    lowThreshold\n'
            '  }\n'
            '  PaymentSession "1" --> "0..*" CoinTube : dispensesChangeFrom\n'
            '```\n\n'
            'Tracks idempotency keys (`transactionId`) and real-time coin tube inventory.\n'
        ),
        states_md=(
            '# VM-002 — Payment Session Lifecycle\n\n'
            '```mermaid\n'
            'stateDiagram-v2\n'
            '  [*] --> PENDING\n'
            '  PENDING --> AUTHORIZED : AuthApproved\n'
            '  PENDING --> DECLINED : AuthRejected\n'
            '  AUTHORIZED --> CAPTURED : DropConfirmed\n'
            '  AUTHORIZED --> VOIDED : DropTimeoutOrCancel\n'
            '  CAPTURED --> [*]\n'
            '  VOIDED --> [*]\n'
            '```\n\n'
            'Replay of `AuthApproved` in `AUTHORIZED` or `CAPTURED` state is a safe no-op.\n'
        ),
    )

    vm3 = Artifact(
        process_id='VM-003',
        workflow_md=(
            '# VM-003 — Restocking & Maintenance Clearing\n\n'
            '**Objective:** Allow authenticated technicians to safely pause sales, clear jams, replenish stock & coins, and synchronize counts to OPS.\n\n'
            '```mermaid\n'
            'flowchart LR\n'
            '  Tech["Service Technician | RFID badge / PIN"]\n'
            '  SVM["Vending Controller | SERVICE_MODE"]\n'
            '  OPS["Operations Portal | inventory & alarms"]\n\n'
            '  Tech -->|Authenticate + DoorOpened| SVM\n'
            '  Tech -->|SubmitRestockCount + DoorClosed| SVM\n'
            '  SVM -->|InventorySynced| OPS\n'
            '```\n\n'
            '## Security & Validation\n\n'
            '- **Unauthenticated Door Open (`SOURCE_DEFINED`)**: Immediately triggers `TamperAlarm` to OPS and disables dispensing.\n'
            '- **Capacity Check (`SOURCE_DEFINED`)**: Rejects any restock quantity exceeding physical slot capacity.\n'
        ),
        boundaries_md=(
            '# VM-003 — Service & Security Boundaries\n\n'
            '```mermaid\n'
            'flowchart LR\n'
            '  Tech[Service Technician] -->|RFID / PIN| SVM[Vending Controller]\n'
            '  SVM -->|InventorySynced / TamperAlarm| OPS[Operations Portal]\n'
            '```\n\n'
            'SVM enforces physical door-switch tamper detection independently of cloud connectivity.\n'
        ),
        domain_md=(
            '# VM-003 — Service Domain Model\n\n'
            '```mermaid\n'
            'classDiagram\n'
            '  direction LR\n'
            '  class ServiceSession {\n'
            '    sessionId\n'
            '    technicianId\n'
            '    openedAt\n'
            '    closedAt\n'
            '  }\n'
            '  class StockAdjustment {\n'
            '    slotCode\n'
            '    delta\n'
            '    reason\n'
            '  }\n'
            '  ServiceSession "1" --> "0..*" StockAdjustment : records\n'
            '```\n\n'
            'Every stock adjustment is immutable and linked to a `ServiceSession` for full auditability.\n'
        ),
        states_md=(
            '# VM-003 — Machine Operating Mode State Machine\n\n'
            '```mermaid\n'
            'stateDiagram-v2\n'
            '  [*] --> IDLE\n'
            '  IDLE --> SERVICE_MODE : TechAuthenticatedAndDoorOpen\n'
            '  IDLE --> TAMPER_LOCKED : UnauthenticatedDoorOpen\n'
            '  SERVICE_MODE --> SELF_CHECK : DoorClosed\n'
            '  SELF_CHECK --> IDLE : ChecksPassed\n'
            '  TAMPER_LOCKED --> SERVICE_MODE : TechAuthenticated\n'
            '```\n\n'
            'Prevents any customer transaction while `SERVICE_MODE` or `TAMPER_LOCKED` is active.\n'
        ),
    )

    for art in (vm1, vm2, vm3):
        store.write(p, f'artifact_{art.process_id}', art.model_dump(), f'generated 4 architecture artifacts for {art.process_id}')
        for kind, field in [('workflow', 'workflow_md'), ('boundaries', 'boundaries_md'), ('domain', 'domain_md'), ('states', 'states_md')]:
            blocks = extract_mermaid_blocks(getattr(art, field))
            if blocks:
                xml = mermaid_to_drawio_xml(blocks[0], title=f'{art.process_id} {kind.title()}', diagram_kind=kind)
                store.write_diagram(p, f'{art.process_id}_{kind}', xml, 'initial diagram generated from artifact')

    # Verify ZERO static check warnings!
    static = quality_checks(cat, {'VM-001': vm1, 'VM-002': vm2, 'VM-003': vm3}, [src])
    assert static == [], f'Expected zero static warnings, got: {static}'

    qa = QualityReport(
        score=94,
        summary='All 3 Vending Machine workflows have complete, consistent state machines, boundaries, and zero deterministic citation or diagram defects. Three workshop open items (O-01..O-03) remain tracked.',
        critical=[],
        warnings=['O-01 spiral retry count must be finalized before dispenser driver timeout tuning.'],
        coverage_gaps=[],
        model_issues=['Confirm whether partial cash-change failure issues a printed voucher or blocks cash vends.'],
        recommendations=['Keep transactionId idempotency ledger persistent across power loss via SQLite/WAL.'],
    )
    store.write(p, 'quality', qa.model_dump(), 'QA assessment across all 3 workflows')
    store.write(p, 'artifacts_approved', True, 'human approved architecture')

    found = Foundation(
        constitution_md=(
            '# Smart Vending Machine — Architecture Constitution\n\n'
            '1. **Zero Ghost Charges**: Never capture payment without a hardware-verified `DropConfirmed` event.\n'
            '2. **Offline Cash Continuity**: Cash vends and local audit logs must operate when cloud connectivity is absent.\n'
            '3. **Explicit State Machines**: All vend, payment, and service mode transitions are transactionally persisted.\n'
            '4. **Source Traceability**: Every requirement distinguishes `SOURCE_DEFINED`, `DESIGN_PROPOSED`, and `UNRESOLVED`.\n'
        ),
        specification_md=(
            '# Smart Vending Machine — Functional Specification\n\n'
            '## FR-001: Slot Selection & Validation\n'
            '- Validate slot stock > 0, slot health == `AVAILABLE`, and cabinet temperature <= 8°C for chilled products.\n\n'
            '## FR-002: Drop-Verified Dispensing\n'
            '- Actuate slot spiral only after `PaymentAuthorized`.\n'
            '- Wait up to 5 seconds for infrared `DropConfirmed`; void/refund and raise `SlotFaultAlarm` on timeout.\n\n'
            '## FR-003: Idempotent Payment & Change\n'
            '- Pre-authorize contactless cards; deduplicate repeated confirmation events by `transactionId`.\n'
            '- Warn customer when coin tubes fall below change threshold.\n\n'
            '## FR-004: Authenticated Restocking & Tamper Protection\n'
            '- Require RFID/PIN authentication for `SERVICE_MODE`; emit `TamperAlarm` on unauthorized door open.\n'
        ),
        clarification_md=(
            '# Open Decisions & Clarification Register\n\n'
            '| ID | Open Question | Impact | Status |\n'
            '| --- | --- | --- | --- |\n'
            '| O-01 | Max spiral retry count before jam (1 retry vs immediate refund)? | Dispenser driver & customer UX | Open |\n'
            '| O-02 | Multi-item cart vs strictly single-item vends in V1? | Payment pre-auth & UI flow | Open |\n'
            '| O-03 | Offline contactless card floor limit permitted? | PGW adapter & chargeback risk | Open |\n'
        ),
    )
    store.write(p, 'foundation', found.model_dump(), 'Spec Kit phase 1 generated')
    store.write(p, 'foundation_approved', True, 'human approved foundation')

    plan = Planning(
        plan_md=(
            '# Technical Implementation Plan — Smart Vending Machine\n\n'
            '## Proposed Architecture\n'
            '- **Controller Runtime**: Modular monolith (.NET 8 or Python/Rust service) on embedded Linux SBC.\n'
            '- **Local Persistence**: SQLite in WAL mode (transactional vend ledger, slot stock, durable OPS outbox).\n'
            '- **Hardware Adapters**: Isolated serial/MDB adapter for `CASH` and GPIO/RS-485 adapter for `DISP`.\n'
            '- **Cloud Sync**: Background outbox worker publishing `SaleRecorded`, `InventorySynced`, and alarms over HTTPS/MQTT.\n'
        ),
        tasks_md=(
            '# Ordered Delivery Tasks (Vertical Slice First)\n\n'
            '1. **TASK-001 (Vertical Slice)**: Implement `Slot`, `VendTransaction` state machine, and simulated `DISP` + `PGW` adapters with unit tests proving zero ghost charges on drop timeout.\n'
            '2. **TASK-002**: Implement idempotent `PaymentSession` + `CashLedger` with duplicate confirmation replay tests.\n'
            '3. **TASK-003**: Implement `SERVICE_MODE`, restock validation, and `TamperAlarm` detection.\n'
            '4. **TASK-004**: Implement durable offline outbox sync worker to `OPS`.\n'
        ),
    )
    store.write(p, 'planning', plan.model_dump(), 'Spec Kit phase 2 planning')
    store.write(p, 'planning_approved', True, 'human approved planning')

    # Initialize local Git repo so Git Sync modal shows real commits too!
    connect_git(p, '', 'main')
    commit_project(p, 'Initial Smart Vending Machine architecture baseline', push=False)
    return p


def record_video():
    import base64

    DEMO_DIR.mkdir(exist_ok=True)
    frames_dir = DEMO_DIR / 'raw_frames'
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)

    frames: list[tuple[float, Path]] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='chrome', headless=True)
        context = browser.new_context(viewport={'width': 1440, 'height': 900})
        page = context.new_page()
        page.add_init_script(f"localStorage.setItem('ae_project', '{PROJECT_SLUG}');")

        cdp = context.new_cdp_session(page)

        def on_frame(params):
            sid = params['sessionId']
            ts = float((params.get('metadata') or {}).get('timestamp') or time.time())
            img_path = frames_dir / f'frame_{len(frames):05d}.jpg'
            img_path.write_bytes(base64.b64decode(params['data']))
            frames.append((ts, img_path))
            try:
                cdp.send('Page.screencastFrameAck', {'sessionId': sid})
            except Exception:
                pass

        cdp.on('Page.screencastFrame', on_frame)
        cdp.send('Page.startScreencast', {
            'format': 'jpeg',
            'quality': 92,
            'maxWidth': 1440,
            'maxHeight': 900,
            'everyNthFrame': 1,
        })

        def snap_pause(sec=1.6):
            # Capture an explicit keyframe + wait so static reading frames hold cleanly
            img_path = frames_dir / f'frame_{len(frames):05d}.jpg'
            page.screenshot(path=str(img_path), type='jpeg', quality=92)
            frames.append((time.time(), img_path))
            time.sleep(sec)

        # 1. Step 1: Clean Upload View (no dark inspector!)
        page.goto('http://127.0.0.1:8501/', wait_until='networkidle')
        snap_pause(2.4)

        # 2. Step 2: Process Catalogue Review
        page.click('.wstep[data-step="2"]')
        snap_pause(2.2)
        page.click('#process-list .list-item >> nth=1')
        snap_pause(1.8)
        page.click('[data-cattab="context"]')
        snap_pause(2.0)
        page.click('[data-cattab="processes"]')
        snap_pause(1.0)

        # 3. Step 3: Open Canvas Studio
        page.click('.wstep[data-step="3"]')
        snap_pause(2.2)

        # 3a. Flows Map (Open Canvas)
        page.click('[data-cmode="map"]')
        snap_pause(2.6)

        # 3b. Word View on VM-001 (Inter + warm paper + hand-drawn Excalidraw diagram!)
        page.click('[data-cmode="word"]')
        snap_pause(2.6)

        # Smooth scroll to inspect full document & tables
        page.evaluate("document.querySelector('#cmode-word').scrollTo({top: 340, behavior: 'smooth'})")
        snap_pause(2.0)
        page.evaluate("document.querySelector('#cmode-word').scrollTo({top: 0, behavior: 'smooth'})")
        snap_pause(1.2)

        # 3c. Boundaries, Domain, States diagrams
        page.click('[data-kind="boundaries"]')
        snap_pause(2.0)
        page.click('[data-kind="domain"]')
        snap_pause(2.0)
        page.click('[data-kind="states"]')
        snap_pause(2.0)
        page.click('[data-kind="workflow"]')
        snap_pause(1.4)

        # 3d. Edit Diagram Inline right inside the Word document!
        page.click('[data-inline-edit="1"]')
        snap_pause(2.0)
        page.click('.doc-diagram-inline-editor [data-add="policy"]')
        snap_pause(1.4)
        page.click('.doc-diagram-inline-editor #nde-undo-btn')
        snap_pause(1.0)
        page.click('.doc-diagram-inline-editor #nde-close-btn')
        snap_pause(1.2)

        # 3e. True Full-Screen Diagram Canvas & Toyota Red Back button
        page.click('[data-full-edit="1"]')
        snap_pause(2.2)
        page.click('#cmode-diagram button:has-text("Back to Document")')
        snap_pause(1.4)

        # 3f. Right-click Context Menu -> Comments drawer
        page.click('#art-process-rail .flow-item >> nth=0', button='right')
        snap_pause(1.8)
        page.click('#item-context-menu .ctx-item:has-text("Comments")')
        snap_pause(1.4)
        page.fill('#cd-input', 'Confirm whether O-01 allows 1 spiral retry before refunding.')
        snap_pause(0.9)
        page.click('#btn-cd-add')
        snap_pause(1.8)
        page.click('#btn-comments-close')
        snap_pause(0.8)

        # 4. Step 4: Quality, Batch Runs & Color-Coded Diff
        page.click('.wstep[data-step="4"]')
        snap_pause(2.2)
        page.select_option('#compare-mode', 'diff')
        snap_pause(2.2)

        # 5. Step 5: Spec Kit Foundation
        page.click('.wstep[data-step="5"]')
        snap_pause(2.0)
        page.click('[data-foundfield="specification_md"]')
        snap_pause(2.0)
        page.click('[data-foundfield="clarification_md"]')
        snap_pause(2.0)

        # 6. Step 6: Plan & Implement + Git Sync modal
        page.click('.wstep[data-step="6"]')
        snap_pause(2.0)
        page.click('[data-planmode="tasks_md"]')
        snap_pause(2.0)
        page.click('#btn-git')
        snap_pause(2.4)
        page.click('#btn-git-close')
        snap_pause(1.2)

        cdp.send('Page.stopScreencast')
        context.close()
        browser.close()

    # Build ffmpeg concat file with real frame durations
    concat_file = frames_dir / 'frames.txt'
    lines = []
    for idx, (ts, fpath) in enumerate(frames):
        if idx + 1 < len(frames):
            dur = max(0.04, min(3.0, frames[idx + 1][0] - ts))
        else:
            dur = 1.2
        lines.append(f"file '{fpath.resolve()}'")
        lines.append(f'duration {dur:.3f}')
    if frames:
        lines.append(f"file '{frames[-1][1].resolve()}'")
    concat_file.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    mp4_out = DEMO_DIR / 'vending-machine-demo.mp4'
    subprocess.run(
        [
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', str(concat_file),
            '-vf', 'fps=24,scale=1440:900:flags=lanczos',
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
            '-preset', 'medium', '-crf', '20',
            '-movflags', '+faststart',
            str(mp4_out),
        ],
        check=True,
        capture_output=True,
    )
    shutil.rmtree(frames_dir, ignore_errors=True)
    return mp4_out


if __name__ == '__main__':
    seed_vending_project()
    out = record_video()
    print('RECORDED VIDEO:', out, f'({out.stat().st_size / 1024:.0f} KB)')
