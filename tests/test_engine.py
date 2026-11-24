import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

from engine.diagrams import extract_mermaid_blocks, mermaid_to_drawio_xml, validate_mermaid_syntax
from engine.export import export_markdown_docx_bytes, export_project_docx, export_speckit, save_code
from engine.git_sync import _validate_remote_url, commit_project, connect_git, sync_readable_docs
from engine.llm import _to_strict_openai_schema, detect_providers, extract_json_payload
from engine.model import Artifact, Catalogue, CodeBundle, Evidence, Process, Rule
from engine.pipeline import extract_catalogue, quality_checks
from engine.sources import pack_chunks, parse_source
from engine.storage import Store
import app as web_app


class FakeLLM:
    def __init__(self, responses):
        self._responses = list(responses)

    def ask(self, system, user, cls):
        return self._responses.pop(0)


class EngineTests(unittest.TestCase):
    def test_text_source_evidence(self):
        source = parse_source('x.md', b'# Hello\nCustomer submits request')
        self.assertEqual(len(source['source_id']), 12)
        self.assertIn('Customer submits', next(pack_chunks([source])))

    def test_sample_pdf_preserves_tables(self):
        pdf_path = Path('examples/sample_document.pdf')
        if not pdf_path.exists():
            self.skipTest('examples/sample_document.pdf not present')
        src = parse_source(pdf_path.name, pdf_path.read_bytes())
        self.assertEqual(len(src['chunks']), 8)
        page2 = src['chunks'][1]['text']
        # Responsibility split table must preserve column alignment with pipe syntax
        self.assertIn('| 1.1 | Create, update and validate members | x |  |', page2)
        self.assertIn('| 1.2 | Display membership eligibility at issue | x | x |', page2)

    def test_store_revisions_diff_and_cascade(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp)
            p = store.project('My Project')
            store.write(p, 'catalogue', {'a': 1})
            store.write(p, 'catalogue', {'a': 2})
            self.assertEqual(len(store.revisions(p, 'catalogue')), 2)
            self.assertIn('+  "a": 2', store.diff(p, 'catalogue'))

            # Test cascading approval invalidation
            for flag in ('catalogue_approved', 'artifacts_approved', 'foundation_approved', 'planning_approved'):
                store.write(p, flag, True)
            store.invalidate_from(p, 'artifacts', 'edited artifact')
            self.assertTrue(store.read(p, 'catalogue_approved'))
            self.assertFalse(store.read(p, 'artifacts_approved'))
            self.assertFalse(store.read(p, 'foundation_approved'))
            self.assertFalse(store.read(p, 'planning_approved'))

    def test_multichunk_merge_preserves_rules(self):
        c1 = Catalogue(
            project_name='CLEP',
            processes=[
                Process(
                    id='RES-001',
                    name='Reservation Management',
                    steps=['Select type'],
                    rules=[Rule(id='R-1', statement='Check availability')],
                )
            ],
        )
        c2 = Catalogue(
            project_name='CLEP',
            processes=[
                Process(
                    id='RES-001',
                    name='Reservation Management',
                    steps=['Confirm booking'],
                    rules=[Rule(id='R-2', statement='Avoid duplicate reservations')],
                )
            ],
        )
        src1 = {'source_id': 'aaa111', 'filename': 'doc.md', 'chunks': [{'locator': 'page 1', 'text': 'A' * 100}]}
        src2 = {'source_id': 'bbb222', 'filename': 'doc.md', 'chunks': [{'locator': 'page 2', 'text': 'B' * 13000}]}
        merged = extract_catalogue(FakeLLM([c1, c2]), [src1, src2])
        self.assertEqual(len(merged.processes), 1)
        self.assertEqual(len(merged.processes[0].rules), 2)

        # Colliding IDs across differently named processes get normalized to uniform PREFIX-CA-NNN
        d1 = Catalogue(project_name='CLEP', processes=[Process(id='RPT-001', name='Overdue report')])
        d2 = Catalogue(project_name='CLEP', processes=[Process(id='RPT-001', name='Active equipment export')])
        merged2 = extract_catalogue(FakeLLM([d1, d2]), [src1, src2], prefix='PRJ')
        self.assertEqual([p.id for p in merged2.processes], ['PRJ-CA-001', 'PRJ-CA-002'])

    def test_models_and_citation_checks(self):
        src = parse_source('doc.md', b'Member submits reservation')
        cat = Catalogue(
            project_name='Example',
            processes=[
                Process(
                    id='P1',
                    name='Example',
                    steps=['Step 1'],
                    actors=['Member'],
                    evidence=[
                        Evidence(source_id=src['source_id'], locator='lines 1-1', quote='Member'),
                        Evidence(source_id=src['source_id'], locator='doc.md lines 1-1', quote='Member'),
                    ],
                ),
                Process(id='P2', name='Missing Evidence'),
            ],
        )
        art = Artifact(
            process_id='P1',
            workflow_md='# Workflow\n' + ('x' * 120) + '\n```mermaid\nflowchart TD\n  A --> B\n```',
            boundaries_md='# Boundaries\n' + ('x' * 120) + '\n```mermaid\nflowchart LR\n  A --> B\n```',
            domain_md='# Domain\n' + ('x' * 120) + '\n```mermaid\nclassDiagram\n  A --> B\n```',
            states_md='# States\n' + ('x' * 120) + '\n```mermaid\nstateDiagram-v2\n  [*] --> Open\n```',
        )
        issues = quality_checks(cat, {'P1': art}, [src])
        self.assertTrue(any('P2: no source evidence' in x for x in issues))
        self.assertFalse(any('P1:' in x for x in issues))

    def test_mermaid_to_drawio_conversion(self):
        md = 'Text\n```mermaid\nflowchart TD\n  A[Member] -->|Request| B[CLEP]\n  B --> C[RMS]\n```'
        blocks = extract_mermaid_blocks(md)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(validate_mermaid_syntax(blocks[0]), [])
        xml = mermaid_to_drawio_xml(blocks[0], title='Workflow')
        self.assertIn('<mxfile', xml)
        self.assertIn('Member', xml)
        self.assertIn('CLEP', xml)
        self.assertIn('Request', xml)

    def test_docx_and_speckit_export(self):
        single = export_markdown_docx_bytes('Test Doc', '# Heading\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n')
        self.assertTrue(single[:2] == b'PK')  # valid zip/docx magic bytes
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            docx_out = export_project_docx(p, catalogue={'project_name': 'CLEP', 'processes': []})
            self.assertTrue(docx_out.is_file())
            out = export_speckit(
                p,
                {'constitution_md': 'A', 'specification_md': 'B', 'clarification_md': 'C'},
                {'plan_md': 'D', 'tasks_md': 'E'},
                catalogue={'project_name': 'CLEP', 'processes': []},
            )
            self.assertTrue(out.is_file())

    def test_guarded_code_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            with self.assertRaises(ValueError):
                save_code(p, {'../evil.py': 'pass'})
            dest = save_code(p, {'src/demo.py': 'print(1)'})
            self.assertEqual((dest / 'src/demo.py').read_text(), 'print(1)')
            with self.assertRaises(ValueError):
                save_code(p, {'src/demo.py': 'print(2)'})
            save_code(p, {'src/demo.py': 'print(2)'}, overwrite=True)
            self.assertEqual((dest / 'src/demo.py').read_text(), 'print(2)')

    def test_fastapi_wizard_and_diagram_endpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_store = web_app.store
            web_app.store = Store(tmp)
            try:
                client = TestClient(web_app.app)
                r = client.get('/')
                self.assertEqual(r.status_code, 200)
                self.assertIn('SPECiT', r.text)

                r = client.post('/api/projects/clep-demo/sources/load-example', json={'filename': 'sample_document.pdf'})
                self.assertEqual(r.status_code, 200)

                st = client.get('/api/projects/clep-demo/state').json()
                self.assertEqual(len(st['sources']), 1)
                self.assertEqual(len(st['sources'][0]['chunks']), 8)

                # Save & retrieve custom Draw.io XML
                xml = mermaid_to_drawio_xml('flowchart TD\n  A --> B', title='Test')
                r = client.put('/api/projects/clep-demo/diagrams/PROC-1/workflow', json={'xml': xml, 'note': 'edit'})
                self.assertEqual(r.status_code, 200)
                d = client.get('/api/projects/clep-demo/diagrams/PROC-1/workflow').json()
                self.assertTrue(d['is_custom'])
                self.assertIn('<mxfile', d['xml'])

                # Export single Word doc
                r = client.post('/api/projects/clep-demo/export/docx-single', json={'title': 'Spec', 'markdown': '# Hello'})
                self.assertEqual(r.status_code, 200)
                self.assertTrue(r.content[:2] == b'PK')

                # Subscription provider discovery endpoint
                pr = client.get('/api/llm/providers').json()
                ids = [p['id'] for p in pr['providers']]
                self.assertIn('copilot_cli', ids)
                self.assertIn('claude_cli', ids)
                self.assertIn('gemini_cli', ids)
                self.assertIn('codex_cli', ids)

                # Comments CRUD
                cm = client.post('/api/projects/clep-demo/comments', json={
                    'target_key': 'artifact::PROC-1::workflow_md',
                    'quote': 'Primary steps',
                    'text': 'Clarify offline fallback step',
                })
                self.assertEqual(cm.status_code, 200)
                cid = cm.json()['id']
                st2 = client.get('/api/projects/clep-demo/state').json()
                self.assertEqual(len(st2['comments']), 1)
                self.assertEqual(client.patch(f'/api/projects/clep-demo/comments/{cid}', json={'status': 'resolved'}).json()['status'], 'resolved')
                self.assertEqual(client.delete(f'/api/projects/clep-demo/comments/{cid}').status_code, 200)

                # Image asset upload & retrieval
                png_1x1 = (
                    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
                    b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?'
                    b'\x00\x05\xfe\x02\xfe\r\xefF\xb8\x00\x00\x00\x00IEND\xaeB`\x82'
                )
                up = client.post('/api/projects/clep-demo/assets/upload', files={'file': ('arch.png', png_1x1, 'image/png')})
                self.assertEqual(up.status_code, 200)
                img_url = up.json()['url']
                self.assertEqual(client.get(img_url).status_code, 200)
                # Export single Word doc embedding that image
                r_img_doc = client.post('/api/projects/clep-demo/export/docx-single', json={'title': 'WithImg', 'markdown': f'# Doc\n\n![Arch]({img_url})'})
                self.assertEqual(r_img_doc.status_code, 200)
                self.assertTrue(r_img_doc.content[:2] == b'PK')

                # Set custom project prefix & verify ZIP export naming: {PREFIX}-SPECIT-YYYYMMDD-HHMMSS.zip
                px_res = client.put('/api/projects/clep-demo/prefix', json={'prefix': 'PPRJ', 'renumber_existing': True})
                self.assertEqual(px_res.status_code, 200)
                self.assertEqual(px_res.json()['prefix'], 'PPRJ')

                # Full project ZIP export & re-import round-trip
                zres = client.get('/api/projects/clep-demo/export/zip')
                self.assertEqual(zres.status_code, 200)
                self.assertTrue(zres.content[:2] == b'PK')
                cd = zres.headers.get('content-disposition', '')
                self.assertRegex(cd, r'PPRJ-SPECIT-\d{8}-\d{6}\.zip')
                imp = client.post('/api/projects/import-zip', files={'file': ('clep-demo-project.zip', zres.content, 'application/zip')})
                self.assertEqual(imp.status_code, 200)
                loaded_slug = imp.json()['project_slug']
                self.assertNotEqual(loaded_slug, 'clep-demo')  # non-destructive import
                loaded_st = client.get(f'/api/projects/{loaded_slug}/state').json()
                self.assertEqual(len(loaded_st['sources']), 1)
                self.assertIn('proc-1-workflow', loaded_st['diagrams'])
            finally:
                web_app.store = old_store

    def test_subscription_json_payload_extraction(self):
        # Claude CLI --output-format json --json-schema envelope
        claude_env = '{"type":"result","structured_output":{"project_name":"CLEP","processes":[]}}'
        self.assertIn('"project_name": "CLEP"', extract_json_payload(claude_env))
        # Gemini CLI envelope
        gemini_env = '{"session_id":"abc","response":"```json\\n{\\"project_name\\":\\"CLEP\\"}\\n```"}'
        self.assertEqual(extract_json_payload(gemini_env), '{"project_name": "CLEP"}')
        # Prose-wrapped JSON
        prose = 'Here is the JSON output:\n{"a": 1, "b": {"c": 2}}\nDone!'
        self.assertEqual(extract_json_payload(prose), '{"a": 1, "b": {"c": 2}}')
        # JSON containing embedded ```mermaid blocks (both raw and outer-fenced)
        art_json = '{"process_id": "EQ-001", "workflow_md": "```mermaid\\nflowchart TD\\n  A --> B\\n```", "boundaries_md": "b", "domain_md": "d", "states_md": "s"}'
        self.assertEqual(extract_json_payload(art_json), art_json)
        self.assertEqual(extract_json_payload(f'```json\n{art_json}\n```'), art_json)
        # Copilot JSONL stream output
        jsonl = '{"type":"assistant.turn_start","data":{}}\n{"type":"assistant.message","data":{"content":"{\\"process_id\\":\\"EQ-001\\"}"}}\n{"type":"result","exitCode":0}'
        self.assertEqual(extract_json_payload(jsonl), '{"process_id": "EQ-001"}')
        # Lenient recovery if a CLI wraps a raw newline inside a JSON string
        wrapped = '{"text": "line one\nline two"}'
        self.assertEqual(extract_json_payload(wrapped), '{"text": "line one\\nline two"}')
        # Provider catalogue detection
        providers = detect_providers()
        self.assertTrue(any(p['id'] == 'copilot_cli' for p in providers))
        self.assertTrue(any(p['id'] == 'codex_cli' for p in providers))
        # OpenAI Codex strict schema helper
        strict_cat = _to_strict_openai_schema(Catalogue.model_json_schema())
        self.assertIsNotNone(strict_cat)
        self.assertIs(strict_cat['additionalProperties'], False)
        self.assertIsNone(_to_strict_openai_schema(CodeBundle.model_json_schema()))

    def test_git_sync_validation_and_docs(self):
        self.assertEqual(_validate_remote_url('https://github.com/org/repo.git'), 'https://github.com/org/repo.git')
        self.assertEqual(_validate_remote_url('git@github.com:org/repo.git'), 'git@github.com:org/repo.git')
        with self.assertRaises(ValueError):
            _validate_remote_url('--upload-pack=evil')
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / 'catalogue.json').write_text('{"project_name":"CLEP","processes":[{"id":"EQ-1","name":"Define"}]}', encoding='utf-8')
            (p / 'artifact_EQ-1.json').write_text('{"process_id":"EQ-1","workflow_md":"# WF","boundaries_md":"# B","domain_md":"# D","states_md":"# S"}', encoding='utf-8')
            written = sync_readable_docs(p)
            self.assertIn('README.md', written)
            self.assertTrue((p / 'docs' / 'architecture' / 'EQ-1' / 'workflow.md').is_file())

    def test_about_endpoint_and_launcher_port(self):
        from fastapi.testclient import TestClient
        import app as web_app
        import launcher

        client = TestClient(web_app.app)
        res = client.get('/api/about')
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body['name'], 'SPECiT')
        self.assertEqual(body['short_name'], 'Si')
        self.assertIn('beta', body['version'].lower())
        self.assertEqual(body['stage'], 'Beta')
        self.assertTrue(body['is_beta'])

        port = launcher.find_available_port(preferred=0)
        self.assertGreater(port, 0)


if __name__ == '__main__':
    unittest.main()
